# SPDX-License-Identifier: LGPL-2.1-or-later

"""Animation playback helpers for MbDFEM result series."""

from bisect import bisect_right
from math import degrees
from time import monotonic

import FreeCAD as App


_POSITION_PROPERTIES = ("xs", "ys", "zs")
_BRYANT_PROPERTIES = ("bryxs", "bryys", "bryzs")
_RESULT_LENGTH_TO_DOCUMENT_LENGTH = 1.0
_KINEMATIC_VECTOR_PROPERTIES = (
    ("velocity", ("vxs", "vys", "vzs"), _RESULT_LENGTH_TO_DOCUMENT_LENGTH),
    ("omega", ("omexs", "omeys", "omezs"), 1.0),
    ("acceleration", ("axs", "ays", "azs"), _RESULT_LENGTH_TO_DOCUMENT_LENGTH),
    ("alpha", ("alpxs", "alpys", "alpzs"), 1.0),
)


class AnimationController:
    """Scrub and play solved MbDFEM result series on document object placements."""

    def __init__(self, assembly, objects=None, length_scale=_RESULT_LENGTH_TO_DOCUMENT_LENGTH):
        if assembly is None:
            raise ValueError("AnimationController expects an MbDFEM assembly")

        self.assembly = assembly
        parameters = self._animation_parameters()
        self.length_scale = float(getattr(parameters, "lengthScale", length_scale))
        self.current_time = 0.0
        self.current_frame = 0
        self.is_playing = False
        self.frames_skipped = 0
        self._timer = None
        self._targets = list(objects) if objects is not None else self._default_targets()
        self._source_frame_count = None
        self._last_tick_time = None
        self._frame_accumulator = 0.0
        if parameters is not None:
            self.setFrame(int(getattr(parameters, "currentFrame", 0)))

    @property
    def targets(self):
        return list(self._targets)

    @property
    def times(self):
        frames = self._playback_frames()
        return [time for _, time in frames]

    @property
    def result_times(self):
        frames = self._result_frames()
        return [time for _, time in frames]

    @property
    def frame_count(self):
        return len(self._playback_frames())

    @property
    def source_frame_count(self):
        if self._source_frame_count is not None:
            return self._source_frame_count

        counts = []
        for target in self._targets:
            for name in _POSITION_PROPERTIES:
                values = getattr(target, name, [])
                count = _sequence_length(values)
                if count:
                    counts.append(count)
        raw_times_count = _sequence_length(getattr(self.assembly, "times", []))
        if raw_times_count:
            counts.append(raw_times_count)
        self._source_frame_count = min(counts) if counts else 0
        return self._source_frame_count

    @property
    def start_frame(self):
        return self.frame_bounds[0]

    @property
    def end_frame(self):
        return self.frame_bounds[1]

    @property
    def frame_bounds(self):
        count = self.source_frame_count
        if count == 0:
            return 0, 0

        parameters = self._animation_parameters()
        start = int(getattr(parameters, "startFrame", 1)) if parameters else 0
        end = int(getattr(parameters, "endFrame", -1)) if parameters else -1

        start = max(0, min(start, count - 1))
        if end < 0:
            end = count - 1
        end = max(start, min(end, count - 1))
        return start, end

    @property
    def duration(self):
        times = self.times
        return times[-1] if times else 0.0

    @property
    def update_rate(self):
        return self.frame_rate

    @property
    def frame_rate(self):
        parameters = self._animation_parameters()
        value = getattr(parameters, "updateRate", 30) if parameters else 30
        return max(float(value), 1.0)

    @property
    def playback_speed(self):
        frames = self._playback_frames()
        if len(frames) < 2:
            return 0.0
        duration = frames[-1][1] - frames[0][1]
        if duration <= 0.0:
            return 0.0
        return self.frame_rate * duration / float(len(frames) - 1)

    @property
    def loop_enabled(self):
        parameters = self._animation_parameters()
        return bool(getattr(parameters, "loop", True)) if parameters else True

    @property
    def interpolate_frames(self):
        parameters = self._animation_parameters()
        return bool(getattr(parameters, "interpolateFrames", True)) if parameters else True

    def setTime(self, seconds):
        """Apply the animation state at *seconds* and return the selected time."""
        times = self.times
        if not times:
            self.current_time = 0.0
            self.current_frame = 0
            return self.current_time

        self.current_time = self._bounded_time(float(seconds))
        sample = self._sample_for_time(self.current_time)
        self.current_frame = sample[3]
        self._apply_sample(sample)
        self._recompute_document()
        return self.current_time

    def setFrame(self, index):
        """Apply the animation state at frame *index*."""
        frames = self._result_frames()
        if not frames:
            self.current_frame = 0
            self.current_time = 0.0
            return self.current_frame

        frame = max(frames[0][0], min(int(index), frames[-1][0]))
        self.current_frame = frame
        self.current_time = frames[frame - frames[0][0]][1]
        self._apply_sample((frame, frame, 0.0, frame))
        parameters = self._animation_parameters()
        if parameters is not None:
            parameters.currentFrame = frame
        self._recompute_document()
        return self.current_frame

    def stepForward(self):
        return self.setFrame(self.current_frame + 1)

    def stepBackward(self):
        return self.setFrame(self.current_frame - 1)

    def play(self):
        """Start timer-driven playback when Qt is available."""
        if self.frame_count == 0:
            return False

        self._prepare_free_body_diagram_scales()
        self._prepare_fem_part_cload_diagram_scales()
        self._prepare_fem_part_dload_diagram_scales()
        timer = self._ensure_timer()
        if timer is None:
            self.is_playing = True
            return False

        interval = max(int(1000.0 / self.frame_rate), 1)
        self.beginPlayback()
        timer.start(interval)
        return True

    def beginPlayback(self):
        if self.current_frame < self.start_frame or self.current_frame > self.end_frame:
            self.setFrame(self.start_frame)
        self.frames_skipped = 0
        self._last_tick_time = monotonic()
        self._frame_accumulator = 0.0
        self.is_playing = True

    def pause(self):
        if self._timer is not None:
            self._timer.stop()
        self.is_playing = False
        self._last_tick_time = None
        self._frame_accumulator = 0.0

    def stop(self):
        self.pause()
        self.setFrame(self.start_frame)

    def tick(self, delta_seconds=None):
        """Advance playback by elapsed real time, skipping simulation frames if needed."""
        if delta_seconds is None:
            now = monotonic()
            if self._last_tick_time is None:
                self._last_tick_time = now
                return self.current_frame
            delta_seconds = now - self._last_tick_time
            self._last_tick_time = now

        self._frame_accumulator += max(float(delta_seconds), 0.0) * self.frame_rate
        frame_advance = int(self._frame_accumulator)
        if frame_advance <= 0:
            return self.current_frame

        self._frame_accumulator -= frame_advance
        previous_frame = self.current_frame
        next_frame, should_pause = self._frame_after_advance(frame_advance)
        self.frames_skipped = self._skipped_between_displayed_frames(previous_frame, next_frame)
        result = self.setFrame(next_frame)
        if should_pause:
            self.pause()
        return result

    def _animation_parameters(self):
        getter = getattr(self.assembly, "getAnimationParameters", None)
        if getter is None:
            return None
        try:
            return getter()
        except Exception:
            return None

    def _default_targets(self):
        targets = []
        for name in ("parts", "fixedparts"):
            for obj in list(getattr(self.assembly, name, [])):
                if obj is not None and obj not in targets and self._has_result_series(obj):
                    targets.append(obj)
        return targets

    @staticmethod
    def _has_result_series(obj):
        return any(_sequence_length(getattr(obj, name, [])) for name in _POSITION_PROPERTIES)

    def _playback_frames(self):
        frames = self._result_frames()
        if not frames:
            return []

        start, end = self.frame_bounds
        return frames[start : end + 1]

    def _result_frames(self):
        raw_times = getattr(self.assembly, "times", [])
        count = self.source_frame_count
        if count == 0:
            return []

        if _sequence_length(raw_times):
            try:
                return [(index, float(raw_times[index])) for index in range(count)]
            except Exception:
                raw_times = list(raw_times)
                return [(index, float(raw_times[index])) for index in range(count)]

        update_rate = self.frame_rate
        return [(index, index / update_rate) for index in range(count)]

    def _frame_after_advance(self, frame_advance):
        start, end = self.frame_bounds
        if frame_advance <= 0 or end <= start:
            return self.current_frame, False

        if self.loop_enabled:
            count = end - start + 1
            offset = (self.current_frame - start + frame_advance) % count
            return start + offset, False

        available = max(end - self.current_frame, 0)
        actual_advance = min(frame_advance, available)
        if actual_advance <= 0:
            return self.current_frame, True
        return self.current_frame + actual_advance, frame_advance >= available

    def _skipped_between_displayed_frames(self, previous_frame, current_frame):
        if current_frame == previous_frame:
            return 0

        if current_frame > previous_frame:
            return current_frame - previous_frame - 1

        start, end = self.frame_bounds
        if not self.loop_enabled or end <= start:
            return 0
        return (end - previous_frame) + (current_frame - start)

    def _bounded_time(self, seconds):
        times = self.times
        if not times:
            return 0.0
        if self.loop_enabled and times[-1] > times[0] and seconds > times[-1]:
            return times[0] + ((seconds - times[0]) % (times[-1] - times[0]))
        return max(times[0], min(seconds, times[-1]))

    def _sample_for_time(self, seconds):
        frames = self._playback_frames()
        if not frames:
            return 0, 0, 0.0, 0
        times = [time for _, time in frames]
        if len(frames) == 1:
            return frames[0][0], frames[0][0], 0.0, frames[0][0]
        upper = bisect_right(times, seconds)
        if upper <= 0:
            return frames[0][0], frames[0][0], 0.0, frames[0][0]
        if upper >= len(frames):
            index = len(frames) - 1
            return frames[index][0], frames[index][0], 0.0, frames[index][0]

        lower = upper - 1
        span = times[upper] - times[lower]
        if span <= 0.0 or not self.interpolate_frames:
            return frames[lower][0], frames[lower][0], 0.0, frames[lower][0]
        return frames[lower][0], frames[upper][0], (seconds - times[lower]) / span, frames[lower][0]

    def _apply_sample(self, sample):
        for target in self._targets:
            placement = App.Placement(target.Placement)
            placement.Base = App.Vector(*self._position(target, sample))
            rotation = self._rotation(target, sample)
            if rotation is not None:
                placement.Rotation = rotation
            target.Placement = placement
            self._apply_kinematic_vectors(target, sample)
        self._update_free_body_diagrams(sample)
        self._update_fem_part_cload_diagrams(sample)
        self._update_fem_part_dload_diagrams(sample)

    def _position(self, target, sample):
        values = []
        for name in _POSITION_PROPERTIES:
            series = getattr(target, name, [])
            values.append(self._sample_value(series, sample) * self.length_scale)
        return values

    def _rotation(self, target, sample):
        series = [getattr(target, name, []) for name in _BRYANT_PROPERTIES]
        if not all(series):
            return None

        lower, upper, ratio = sample[:3]
        lower_rotation = self._rotation_at_index(series, lower)
        if lower == upper:
            return lower_rotation

        upper_rotation = self._rotation_at_index(series, upper)
        return lower_rotation.slerp(upper_rotation, ratio)

    @staticmethod
    def _rotation_at_index(series, index):
        angles = []
        for values in series:
            clamped_index = max(0, min(index, len(values) - 1))
            angles.append(degrees(float(values[clamped_index])))

        x_angle, y_angle, z_angle = angles
        x_rotation = App.Rotation(App.Vector(1, 0, 0), x_angle)
        y_rotation = App.Rotation(App.Vector(0, 1, 0), y_angle)
        z_rotation = App.Rotation(App.Vector(0, 0, 1), z_angle)
        return z_rotation.multiply(y_rotation).multiply(x_rotation)

    def _apply_kinematic_vectors(self, target, sample):
        for target_name, source_names, scale in _KINEMATIC_VECTOR_PROPERTIES:
            series = [getattr(target, name, []) for name in source_names]
            if not any(series):
                continue
            try:
                setattr(
                    target,
                    target_name,
                    App.Vector(
                        *(self._sample_value(values, sample) * scale for values in series)
                    ),
                )
            except Exception:
                pass

    @staticmethod
    def _sample_value(values, sample):
        if not values:
            return 0.0

        lower, upper, ratio = sample[:3]
        lower = max(0, min(lower, len(values) - 1))
        upper = max(0, min(upper, len(values) - 1))
        if lower == upper:
            return float(values[lower])
        return float(values[lower]) + (float(values[upper]) - float(values[lower])) * ratio

    def _ensure_timer(self):
        if self._timer is not None:
            return self._timer
        try:
            from PySide import QtCore
        except Exception:
            return None

        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self.tick)
        return self._timer

    def _recompute_document(self):
        document = getattr(self.assembly, "Document", None)
        if document is not None:
            document.recompute()

    def _update_free_body_diagrams(self, sample):
        try:
            import FreeCADMbDFreeBodyDiagram
        except Exception:
            return

        try:
            FreeCADMbDFreeBodyDiagram.update_active_diagrams(self, sample)
        except Exception as exc:
            App.Console.PrintWarning(f"FreeBodyDiagram update failed: {exc}\n")

    def _prepare_free_body_diagram_scales(self):
        try:
            import FreeCADMbDFreeBodyDiagram
        except Exception:
            return

        try:
            FreeCADMbDFreeBodyDiagram.prepare_diagram_scales(self.assembly, force=True)
        except Exception as exc:
            App.Console.PrintWarning(f"FreeBodyDiagram scale preparation failed: {exc}\n")

    def _prepare_fem_part_dload_diagram_scales(self):
        try:
            import FreeCADMbDFEMDLOADs
        except Exception:
            return

        try:
            FreeCADMbDFEMDLOADs.prepare_diagram_scale(self.assembly, force=True)
        except Exception as exc:
            App.Console.PrintWarning(f"FEMPart DLOAD scale preparation failed: {exc}\n")

    def _prepare_fem_part_cload_diagram_scales(self):
        try:
            import FreeCADMbDFEMCLOADs
        except Exception:
            return

        try:
            FreeCADMbDFEMCLOADs.prepare_diagram_scale(self.assembly, force=True)
        except Exception as exc:
            App.Console.PrintWarning(f"FEMPart CLOAD scale preparation failed: {exc}\n")

    def _update_fem_part_dload_diagrams(self, sample):
        try:
            import FreeCADMbDFEMDLOADs
        except Exception:
            return

        try:
            FreeCADMbDFEMDLOADs.update_active_diagrams(self, sample)
        except Exception as exc:
            App.Console.PrintWarning(f"FEMPart DLOAD diagram update failed: {exc}\n")

    def _update_fem_part_cload_diagrams(self, sample):
        try:
            import FreeCADMbDFEMCLOADs
        except Exception:
            return

        try:
            FreeCADMbDFEMCLOADs.update_active_diagrams(self, sample)
        except Exception as exc:
            App.Console.PrintWarning(f"FEMPart CLOAD diagram update failed: {exc}\n")


def controller(assembly, objects=None, length_scale=_RESULT_LENGTH_TO_DOCUMENT_LENGTH):
    """Create an :class:`AnimationController` for *assembly*."""
    return AnimationController(assembly, objects=objects, length_scale=length_scale)


def _sequence_length(values):
    try:
        return len(values)
    except Exception:
        try:
            return len(list(values))
        except Exception:
            return 0
