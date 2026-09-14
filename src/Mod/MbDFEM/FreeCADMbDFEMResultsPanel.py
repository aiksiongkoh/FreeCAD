# SPDX-License-Identifier: LGPL-2.1-or-later

"""Task panel for solving FEMPart result states over an MbD time series."""

import math
import sys

import FreeCAD as App

import FreeCADMbDAnimation
import FreeCADMbDBackend
import FreeCADMbDFEMEmbedded


_STATE_INDEX_PROPERTY = "MbDFEMStateIndex"
_STATE_TIME_PROPERTY = "MbDFEMStateTime"
_DEFAULT_PIPELINE_FIELD = "von Mises Stress"
_PIPELINE_SCALAR_FIELD_PROPERTIES = {
    "Displacement Magnitude": "DisplacementLengths",
    "von Mises Stress": "vonMises",
    "Major Principal Stress": "PrincipalMax",
    "Intermediate Principal Stress": "PrincipalMed",
    "Minor Principal Stress": "PrincipalMin",
    "Tresca Stress": "MaxShear",
    "Stress xx component": "NodeStressXX",
    "Stress yy component": "NodeStressYY",
    "Stress zz component": "NodeStressZZ",
    "Stress xy component": "NodeStressXY",
    "Stress xz component": "NodeStressXZ",
    "Stress yz component": "NodeStressYZ",
}
_FRD_STRESS_COMPONENT_INDEX = {
    "Stress xx component": 0,
    "Stress yy component": 1,
    "Stress zz component": 2,
    "Stress xy component": 3,
    "Stress xz component": 4,
    "Stress yz component": 5,
}
_PIPELINE_FIELD_SCALE = {
    "Displacement Magnitude": 0.001,
    "von Mises Stress": 1.0e6,
    "Major Principal Stress": 1.0e6,
    "Intermediate Principal Stress": 1.0e6,
    "Minor Principal Stress": 1.0e6,
    "Tresca Stress": 1.0e6,
    "Stress xx component": 1.0e6,
    "Stress yy component": 1.0e6,
    "Stress zz component": 1.0e6,
    "Stress xy component": 1.0e6,
    "Stress xz component": 1.0e6,
    "Stress yz component": 1.0e6,
}
_PIPELINE_FIELD_DISPLAY_UNITS = {
    "Displacement Magnitude": "m",
    "von Mises Stress": "Pa",
    "Major Principal Stress": "Pa",
    "Intermediate Principal Stress": "Pa",
    "Minor Principal Stress": "Pa",
    "Tresca Stress": "Pa",
    "Stress xx component": "Pa",
    "Stress yy component": "Pa",
    "Stress zz component": "Pa",
    "Stress xy component": "Pa",
    "Stress xz component": "Pa",
    "Stress yz component": "Pa",
}
_FRD_SCALAR_RANGE_CACHE = {}
_FIXED_COLOR_RANGE_ENABLED_PROPERTY = "MbDFEMFixedColorBarRangeEnabled"
_FIXED_COLOR_RANGE_MINIMUM_PROPERTY = "MbDFEMFixedColorBarMinimum"
_FIXED_COLOR_RANGE_MAXIMUM_PROPERTY = "MbDFEMFixedColorBarMaximum"
_FIXED_COLOR_RANGE_FIELD_PROPERTY = "MbDFEMFixedColorBarField"
_RESULTS_PANEL_STATE_PROPERTIES = {
    "current": "MbDFEMResultsPanelCurrentState",
    "start": "MbDFEMResultsPanelStartState",
    "end": "MbDFEMResultsPanelEndState",
}


def owning_fem_part(results_folder):
    document = getattr(results_folder, "Document", None)
    if document is None:
        return None

    for obj in getattr(document, "Objects", []):
        try:
            if obj.isDerivedFrom("MbDFEM::FEMPart") and obj.getResultsFolder() == results_folder:
                return obj
        except Exception:
            pass
    return None


def owning_mbd_assembly(fem_part):
    mbd_part = getattr(fem_part, "mbdItem", None)
    document = getattr(fem_part, "Document", None)
    if document is None or mbd_part is None:
        return None

    for obj in getattr(document, "Objects", []):
        try:
            if not obj.isDerivedFrom("MbDFEM::MbDAssembly"):
                continue
            if mbd_part in list(getattr(obj, "parts", [])) or mbd_part in list(
                getattr(obj, "fixedparts", [])
            ):
                return obj
        except Exception:
            pass
    return None


def state_count(fem_part):
    assembly = owning_mbd_assembly(fem_part)
    if assembly is None:
        return 0

    counts = []
    times = list(getattr(assembly, "times", []))
    if times:
        counts.append(len(times))

    mbd_part = getattr(fem_part, "mbdItem", None)
    if mbd_part is not None:
        for name in ("xs", "ys", "zs", "bryxs", "bryys", "bryzs"):
            values = list(getattr(mbd_part, name, []))
            if values:
                counts.append(len(values))

    return min(counts) if counts else 0


def apply_state(fem_part, state_index):
    assembly = owning_mbd_assembly(fem_part)
    if assembly is None:
        raise ValueError("No owning MbDAssembly found for FEMPart.")

    controller = FreeCADMbDAnimation.AnimationController(assembly)
    if state_index < 0 or state_index >= controller.source_frame_count:
        raise IndexError("MbD state index not in range.")

    controller.setFrame(state_index)
    _sync_fem_parts_to_mbd_parts(assembly, controller.targets)
    return assembly


def _sync_fem_parts_to_mbd_parts(assembly, mbd_parts):
    document = getattr(assembly, "Document", None)
    if document is None:
        return

    mbd_parts = [part for part in mbd_parts if part is not None]
    for obj in getattr(document, "Objects", []):
        try:
            if not obj.isDerivedFrom("MbDFEM::FEMPart"):
                continue
            mbd_part = getattr(obj, "mbdItem", None)
            if mbd_part in mbd_parts:
                obj.Placement = App.Placement(mbd_part.Placement)
        except Exception:
            pass
    document.recompute()


def _linked_results(fem_part):
    return FreeCADMbDFEMEmbedded._linked_results(fem_part)


def _result_state_index(result, fallback_index=None):
    try:
        return int(getattr(result, _STATE_INDEX_PROPERTY))
    except Exception:
        return fallback_index


def _result_for_state(fem_part, state_index, base_results=None):
    results = list(base_results) if base_results is not None else _linked_results(fem_part)
    for fallback_index, result in enumerate(results):
        if _result_state_index(result, fallback_index) == state_index:
            return result
    return None


def _is_result_series(fem_part):
    return state_count(fem_part) > 1


def _include_state_in_legend_scale(fem_part, state_index):
    if state_index is None:
        return True
    return not (_is_result_series(fem_part) and int(state_index) == 0)


def _ordered_results_for_storage(results):
    def sort_key(item):
        fallback_index, result = item
        state_index = _result_state_index(result, fallback_index)
        return (state_index if state_index is not None else fallback_index, fallback_index)

    return [result for _, result in sorted(enumerate(results), key=sort_key)]


def _set_result_state_metadata(fem_part, result, state_index):
    if _STATE_INDEX_PROPERTY not in list(getattr(result, "PropertiesList", [])):
        try:
            result.addProperty(
                "App::PropertyInteger",
                _STATE_INDEX_PROPERTY,
                "MbDFEM",
                "MbD time-state index solved by this result",
            )
        except Exception:
            pass
    if _STATE_TIME_PROPERTY not in list(getattr(result, "PropertiesList", [])):
        try:
            result.addProperty(
                "App::PropertyFloat",
                _STATE_TIME_PROPERTY,
                "MbDFEM",
                "MbD time value solved by this result",
            )
        except Exception:
            pass
    try:
        setattr(result, _STATE_INDEX_PROPERTY, int(state_index))
    except Exception:
        pass
    try:
        setattr(result, _STATE_TIME_PROPERTY, float(_state_time(fem_part, state_index)))
    except Exception:
        pass


def _property_enum_names(prop):
    try:
        return list(prop.getEnumVector())
    except Exception:
        pass
    try:
        return [str(prop.getItemText(index)) for index in range(prop.count())]
    except Exception:
        pass
    return []


def _property_enum_value(prop):
    try:
        return str(prop.getValueAsString())
    except Exception:
        pass
    try:
        value = prop.getValue()
        names = _property_enum_names(prop)
        if 0 <= value < len(names):
            return names[value]
    except Exception:
        pass
    return ""


def _set_property_enum_value(prop, value):
    if not value:
        return False
    try:
        prop.setValue(value)
        return True
    except Exception:
        pass
    try:
        names = _property_enum_names(prop)
        if value in names:
            prop.setValue(names.index(value))
            return True
    except Exception:
        pass
    return False


def _pipeline_field_name(pipeline):
    view_object = getattr(pipeline, "ViewObject", None)
    field = getattr(view_object, "Field", None)
    if field is None:
        return ""
    value = _property_enum_value(field)
    return "" if value == "None" else value


def _result_scalar_values(result, field_name):
    prop_name = _PIPELINE_SCALAR_FIELD_PROPERTIES.get(field_name)
    if not prop_name:
        return []
    try:
        return list(getattr(result, prop_name, []))
    except Exception:
        return []


def _finite_min_max(values):
    finite_values = []
    for value in values:
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            finite_values.append(value)
    if not finite_values:
        return None
    return min(finite_values), max(finite_values)


def _pipeline_field_scale(field_name):
    return _PIPELINE_FIELD_SCALE.get(field_name, 1.0)


def _pipeline_field_display_label(field_name):
    unit = _PIPELINE_FIELD_DISPLAY_UNITS.get(field_name)
    return f"{field_name} [{unit}]" if unit else field_name


def _decorate_pipeline_field_combo(combo_box):
    try:
        from PySide import QtCore
    except Exception:
        QtCore = None

    role = QtCore.Qt.UserRole if QtCore is not None else 0x0100
    for index in range(combo_box.count()):
        field_name = combo_box.itemData(index, role)
        if not field_name:
            field_name = combo_box.itemText(index)
            combo_box.setItemData(index, field_name, role)
        combo_box.setItemText(index, _pipeline_field_display_label(str(field_name)))


def _pipeline_field_combo_value(combo_box):
    try:
        from PySide import QtCore

        value = combo_box.itemData(combo_box.currentIndex(), QtCore.Qt.UserRole)
        return str(value) if value else combo_box.currentText()
    except Exception:
        return ""


def _scaled_min_max(values, field_name):
    value_range = _finite_min_max(values)
    if value_range is None:
        return None
    scale = _pipeline_field_scale(field_name)
    return value_range[0] * scale, value_range[1] * scale


def _von_mises_from_stress(stress):
    sxx, syy, szz, sxy, sxz, syz = [float(value) for value in stress]
    return math.sqrt(
        (
            (sxx - syy) ** 2
            + (syy - szz) ** 2
            + (szz - sxx) ** 2
            + 6.0 * (sxy**2 + sxz**2 + syz**2)
        )
        / 2.0
    )


def _frd_scalar_values_for_result_set(result_set, field_name):
    if field_name == "Displacement Magnitude":
        values = []
        for vector in getattr(result_set.get("disp", {}), "values", lambda: [])():
            try:
                values.append(float(vector.Length))
            except Exception:
                try:
                    values.append(math.sqrt(sum(float(component) ** 2 for component in vector)))
                except Exception:
                    pass
        return values

    stresses = list(getattr(result_set.get("stress", {}), "values", lambda: [])())
    if field_name == "von Mises Stress":
        values = []
        for stress in stresses:
            try:
                values.append(_von_mises_from_stress(stress))
            except Exception:
                pass
        return values

    component = _FRD_STRESS_COMPONENT_INDEX.get(field_name)
    if component is not None:
        values = []
        for stress in stresses:
            try:
                values.append(float(stress[component]))
            except Exception:
                pass
        return values

    return []


def _read_frd_result_sets(frd_file):
    from feminout import importCcxFrdResults

    return importCcxFrdResults.read_frd_result(str(frd_file)).get("Results", [])


def _frd_file_for_state(fem_part, state_index):
    working_dir = FreeCADMbDBackend.calculix_working_dir_path(fem_part, state_index)
    return working_dir / f"{FreeCADMbDBackend.CALCULIX_BASE_NAME}.frd"


def _frd_scalar_range(frd_file, field_name):
    try:
        stat = frd_file.stat()
    except OSError:
        return None

    key = (str(frd_file), field_name, stat.st_mtime_ns, stat.st_size)
    if key in _FRD_SCALAR_RANGE_CACHE:
        return _FRD_SCALAR_RANGE_CACHE[key]

    try:
        values = []
        for result_set in _read_frd_result_sets(frd_file):
            values.extend(_frd_scalar_values_for_result_set(result_set, field_name))
        value_range = _scaled_min_max(values, field_name)
    except Exception as exc:
        App.Console.PrintWarning(f"Unable to read FEM result range from {frd_file}: {exc}\n")
        value_range = None

    _FRD_SCALAR_RANGE_CACHE[key] = value_range
    return value_range


def _solved_frd_scalar_ranges(fem_part, field_name):
    count = state_count(fem_part)
    ranges = []
    for state_index in range(count):
        if not _include_state_in_legend_scale(fem_part, state_index):
            continue
        frame_range = _frd_scalar_range(_frd_file_for_state(fem_part, state_index), field_name)
        if frame_range is not None:
            ranges.append(frame_range)
    return ranges


def _global_pipeline_scalar_range(fem_part, field_name):
    ranges = []
    for fallback_index, result in enumerate(_linked_results(fem_part)):
        if not _include_state_in_legend_scale(
            fem_part,
            _result_state_index(result, fallback_index),
        ):
            continue
        frame_range = _scaled_min_max(_result_scalar_values(result, field_name), field_name)
        if frame_range is not None:
            ranges.append(frame_range)
    ranges.extend(_solved_frd_scalar_ranges(fem_part, field_name))
    if not ranges:
        return None
    minimum = min(frame_range[0] for frame_range in ranges)
    maximum = max(frame_range[1] for frame_range in ranges)
    if minimum == maximum:
        padding = abs(minimum) * 0.01 or 1.0
        minimum -= padding
        maximum += padding
    return minimum, maximum


def _set_pipeline_fixed_color_range(pipeline, value_range):
    view_object = getattr(pipeline, "ViewObject", None)
    if view_object is None:
        return

    def post_objects():
        objects = [pipeline]
        try:
            objects.extend(list(getattr(pipeline, "Group", [])))
        except Exception:
            pass
        return [obj for obj in objects if obj is not None]

    def ensure_app_property(obj, property_type, name):
        if hasattr(obj, name):
            return
        try:
            obj.addProperty(
                property_type,
                name,
                "MbDFEM",
                "Fixed color bar range used by MbDFEM animated result display.",
            )
        except Exception:
            pass

    def set_app_range(value_range):
        field_name = _pipeline_field_name(pipeline) or _DEFAULT_PIPELINE_FIELD
        for obj in post_objects():
            ensure_app_property(obj, "App::PropertyBool", _FIXED_COLOR_RANGE_ENABLED_PROPERTY)
            ensure_app_property(obj, "App::PropertyFloat", _FIXED_COLOR_RANGE_MINIMUM_PROPERTY)
            ensure_app_property(obj, "App::PropertyFloat", _FIXED_COLOR_RANGE_MAXIMUM_PROPERTY)
            ensure_app_property(obj, "App::PropertyString", _FIXED_COLOR_RANGE_FIELD_PROPERTY)
            try:
                setattr(obj, _FIXED_COLOR_RANGE_FIELD_PROPERTY, field_name)
                if value_range is None:
                    setattr(obj, _FIXED_COLOR_RANGE_ENABLED_PROPERTY, False)
                    continue
                minimum, maximum = value_range
                setattr(obj, _FIXED_COLOR_RANGE_MINIMUM_PROPERTY, float(minimum))
                setattr(obj, _FIXED_COLOR_RANGE_MAXIMUM_PROPERTY, float(maximum))
                setattr(obj, _FIXED_COLOR_RANGE_ENABLED_PROPERTY, True)
            except Exception as exc:
                App.Console.PrintWarning(
                    "MbDFEM: unable to update fixed color range on "
                    f"{getattr(obj, 'Name', '<unnamed>')}: {exc}\n"
                )

    def set_view_property(name, value):
        try:
            view_object.setPropertyByName(name, value)
            return True
        except Exception:
            pass
        try:
            setattr(view_object, name, value)
            return True
        except Exception:
            return False

    try:
        set_app_range(value_range)
        if value_range is None:
            set_view_property("UseFixedColorBarRange", False)
        else:
            minimum, maximum = value_range
            set_view_property("FixedColorBarMinimum", float(minimum))
            set_view_property("FixedColorBarMaximum", float(maximum))
            set_view_property("UseFixedColorBarRange", True)
    except Exception:
        return

    try:
        pipeline.Document.recompute()
    except Exception:
        pass
    try:
        view_object.updateMaterial()
    except Exception:
        pass
    try:
        view_object.updateColorBars()
    except Exception:
        pass


def _apply_global_pipeline_color_range(fem_part, pipeline, value_range=None):
    field_name = _pipeline_field_name(pipeline) or _DEFAULT_PIPELINE_FIELD
    if not field_name:
        return
    if value_range is None:
        value_range = _global_pipeline_scalar_range(fem_part, field_name)
    if value_range is None:
        _set_pipeline_fixed_color_range(pipeline, None)
        return
    _set_pipeline_fixed_color_range(pipeline, value_range)


def _refresh_pipeline_fixed_color_range(fem_part, pipeline, value_range=None):
    _apply_global_pipeline_color_range(fem_part, pipeline, value_range=value_range)
    _refresh_pipeline_legend(pipeline)


def _apply_result_mesh_color_range(fem_part, result, value_range=None):
    if result is None:
        return
    pipeline = getattr(fem_part, "visual", None)
    field_name = _pipeline_field_name(pipeline) if pipeline is not None else _DEFAULT_PIPELINE_FIELD
    attribute = _PIPELINE_SCALAR_FIELD_PROPERTIES.get(field_name)
    if not attribute:
        return
    values = list(getattr(result, attribute, []))
    node_numbers = list(getattr(result, "NodeNumbers", []))
    if not values or len(values) != len(node_numbers):
        return
    scale = _pipeline_field_scale(field_name)
    if scale != 1.0:
        values = [float(value) * scale for value in values]
    if value_range is None:
        value_range = _global_pipeline_scalar_range(fem_part, field_name)
    if value_range is None:
        return
    result_mesh = getattr(result, "Mesh", None)
    mesh_view = getattr(result_mesh, "ViewObject", None)
    if mesh_view is None:
        return
    minimum, maximum = value_range
    try:
        mesh_view.setNodeColorByScalars(node_numbers, values, float(minimum), float(maximum))
    except TypeError:
        mesh_view.setNodeColorByScalars(node_numbers, values)
    except Exception:
        pass


def _schedule_pipeline_fixed_color_range_refresh(fem_part, pipeline, value_range=None):
    try:
        from PySide import QtCore
    except Exception:
        return

    def refresh():
        try:
            _refresh_pipeline_fixed_color_range(fem_part, pipeline, value_range=value_range)
        except Exception:
            pass

    QtCore.QTimer.singleShot(0, refresh)
    QtCore.QTimer.singleShot(50, refresh)


def _select_pipeline_field(pipeline, preferred_field=None):
    view_object = getattr(pipeline, "ViewObject", None)
    field = getattr(view_object, "Field", None)
    if field is None:
        return ""

    names = _property_enum_names(field)
    candidates = [preferred_field, _DEFAULT_PIPELINE_FIELD, "Displacement Magnitude"]
    for candidate in candidates:
        if candidate and candidate in names and _set_property_enum_value(field, candidate):
            component = getattr(view_object, "Component", None)
            if component is not None:
                _set_property_enum_value(component, "Not a vector")
            try:
                view_object.updateMaterial()
            except Exception:
                pass
            try:
                view_object.updateColorBars()
            except Exception:
                pass
            _refresh_pipeline_legend(pipeline)
            return candidate
    return _pipeline_field_name(pipeline)


def _pipeline_field_names(pipeline):
    view_object = getattr(pipeline, "ViewObject", None)
    field = getattr(view_object, "Field", None)
    if field is None:
        return []
    return [name for name in _property_enum_names(field) if name and name != "None"]


def _ensure_visual_pipeline(fem_part, result, preferred_field=None):
    if result is None:
        return None

    document = getattr(fem_part, "Document", None)
    if document is None:
        return None

    pipeline = getattr(fem_part, "visual", None)
    if pipeline is None:
        try:
            pipeline = document.addObject("Fem::FemPostPipeline", "Pipeline_CCX_Results")
            fem_part.visual = pipeline
            try:
                fem_part.addObject(pipeline)
            except Exception:
                pass
        except Exception as exc:
            App.Console.PrintWarning(f"Unable to create FEM result pipeline: {exc}\n")
            return None

    if preferred_field is None:
        preferred_field = _pipeline_field_name(pipeline)
    try:
        pipeline.Label = "Pipeline_CCX_Results"
    except Exception:
        pass
    try:
        pipeline.load(result)
    except Exception as exc:
        App.Console.PrintWarning(f"Unable to load FEM result pipeline: {exc}\n")
        return None
    try:
        pipeline.recomputeChildren()
    except Exception:
        pass
    try:
        pipeline.recompute()
    except Exception:
        pass

    view_object = getattr(pipeline, "ViewObject", None)
    if view_object is not None:
        try:
            view_object.ShowInTree = False
        except Exception:
            pass
        try:
            view_object.DisplayMode = "Surface"
        except Exception:
            pass
        try:
            view_object.SelectionStyle = "BoundBox"
        except Exception:
            pass
        try:
            view_object.Visibility = True
        except Exception:
            pass

    _select_pipeline_field(pipeline, preferred_field)
    _refresh_pipeline_fixed_color_range(fem_part, pipeline)
    _schedule_pipeline_fixed_color_range_refresh(fem_part, pipeline)
    return pipeline


def _refresh_pipeline_legend(pipeline):
    view_object = getattr(pipeline, "ViewObject", None)
    if view_object is None:
        return

    try:
        view_object.Visibility = True
    except Exception:
        pass
    try:
        view_object.show()
    except Exception:
        pass
    try:
        view_object.updateMaterial()
    except Exception:
        pass
    try:
        view_object.updateColorBars()
    except Exception:
        pass
    try:
        import FreeCADGui as Gui

        Gui.ActiveDocument.ActiveView.redraw()
    except Exception:
        pass


def _remove_object_from_group(group, obj):
    try:
        if obj in list(getattr(group, "Group", [])):
            group.removeObject(obj)
            return True
    except Exception:
        pass
    return False


def _remove_result_from_foreign_groups(fem_part, result):
    document = getattr(fem_part, "Document", None)
    if document is None or result is None:
        return

    keep_groups = set()
    try:
        keep_groups.add(fem_part.getResultsFolder())
    except Exception:
        pass
    keep_groups.discard(None)

    for obj in list(getattr(document, "Objects", [])):
        if obj in keep_groups:
            continue
        if obj is result:
            continue
        _remove_object_from_group(obj, result)


def _discard_result_object(result):
    document = getattr(result, "Document", None)
    name = getattr(result, "Name", "")
    mesh = getattr(result, "Mesh", None)
    if document is None or not name:
        return

    try:
        document.removeObject(name)
    except Exception:
        pass

    mesh_name = getattr(mesh, "Name", "")
    try:
        if mesh_name and document.getObject(mesh_name) is not None:
            document.removeObject(mesh_name)
    except Exception:
        pass


def _assign_result_for_state(fem_part, state_index, result, base_results=None):
    if result is None:
        raise ValueError("No CalculiX result object was produced.")

    results = list(base_results) if base_results is not None else _linked_results(fem_part)
    _set_result_state_metadata(fem_part, result, state_index)

    existing = _result_for_state(fem_part, state_index, results)
    if existing is None:
        results.append(result)
    else:
        results[results.index(existing)] = result

    fem_part.results = _ordered_results_for_storage(results)
    try:
        fem_part.synchronizeResultsFolder()
    except Exception:
        pass
    _remove_result_from_foreign_groups(fem_part, result)
    if existing is not None and existing is not result:
        _discard_result_object(existing)
    return result


def _new_result(before_results, fem_part):
    for result in reversed(_linked_results(fem_part)):
        if result not in before_results:
            return result
    return None


def solve_fem_part_state(fem_part, state_index, runner=None):
    document = getattr(fem_part, "Document", None)
    solver = getattr(fem_part, "solver", None)
    if document is None:
        raise ValueError("FEMPart is not attached to a document.")
    if solver is None:
        raise ValueError("FEMPart has no CalculiX solver.")

    apply_state(fem_part, state_index)
    before_results = _linked_results(fem_part)

    if runner is None:
        fea = FreeCADMbDFEMEmbedded.FEMPartCcxTools(fem_part, solver)
        working_dir = FreeCADMbDBackend.default_calculix_working_dir(fem_part, state_index)
        fea.setup_working_dir(str(working_dir))
        fea.set_base_name(FreeCADMbDBackend.CALCULIX_BASE_NAME)
        fea.setup_ccx()
        if not fea.run():
            raise RuntimeError("CalculiX solve failed.")
        result = _new_result(before_results, fem_part)
    else:
        result = runner(fem_part, state_index)

    assigned = _assign_result_for_state(
        fem_part,
        state_index,
        result,
        base_results=before_results,
    )
    try:
        time_text = _state_label_time_text(fem_part, state_index)
        assigned.Label = f"{fem_part.Label} result {state_index} @ {time_text}"
    except Exception:
        pass
    _ensure_visual_pipeline(fem_part, assigned)
    document.recompute()
    return assigned


def import_fem_part_state(fem_part, state_index, runner=None):
    document = getattr(fem_part, "Document", None)
    solver = getattr(fem_part, "solver", None)
    if document is None:
        raise ValueError("FEMPart is not attached to a document.")
    if solver is None:
        raise ValueError("FEMPart has no CalculiX solver.")

    apply_state(fem_part, state_index)
    before_results = _linked_results(fem_part)

    if runner is None:
        fea = FreeCADMbDFEMEmbedded.FEMPartCcxTools(fem_part, solver)
        working_dir = FreeCADMbDBackend.default_calculix_working_dir(fem_part, state_index)
        fea.setup_working_dir(str(working_dir))
        fea.set_base_name(FreeCADMbDBackend.CALCULIX_BASE_NAME)
        fea.setup_ccx()
        fea.inp_file_name = str(working_dir / f"{FreeCADMbDBackend.CALCULIX_BASE_NAME}.inp")
        frd_file = working_dir / f"{FreeCADMbDBackend.CALCULIX_BASE_NAME}.frd"
        if not frd_file.is_file():
            raise FileNotFoundError(f"CalculiX result file not found: {frd_file}")
        fea.load_results_ccxfrd()
        result = _new_result(before_results, fem_part)
    else:
        result = runner(fem_part, state_index)

    assigned = _assign_result_for_state(
        fem_part,
        state_index,
        result,
        base_results=before_results,
    )
    try:
        time_text = _state_label_time_text(fem_part, state_index)
        assigned.Label = f"{fem_part.Label} imported result {state_index} @ {time_text}"
    except Exception:
        pass
    _ensure_visual_pipeline(fem_part, assigned)
    document.recompute()
    return assigned


def _state_time(fem_part, state_index):
    assembly = owning_mbd_assembly(fem_part)
    times = list(getattr(assembly, "times", [])) if assembly is not None else []
    if 0 <= state_index < len(times):
        return float(times[state_index])
    return float(state_index)


def _is_input_state_time(value):
    try:
        return float(value) <= -sys.float_info.max * 0.999
    except Exception:
        return False


def _state_time_text(fem_part, state_index):
    value = _state_time(fem_part, state_index)
    if _is_input_state_time(value):
        return "Input"
    return f"{value:.6g} s"


def _state_label_time_text(fem_part, state_index):
    value = _state_time(fem_part, state_index)
    if _is_input_state_time(value):
        return "Input"
    return f"{value:.6g}s"


def _clamped_results_panel_state(fem_part, key, default, maximum):
    value = getattr(fem_part, _RESULTS_PANEL_STATE_PROPERTIES[key], default)
    try:
        value = int(value)
    except Exception:
        value = default
    return max(0, min(value, maximum))


def _set_results_panel_state(fem_part, key, value):
    property_name = _RESULTS_PANEL_STATE_PROPERTIES[key]
    if not hasattr(fem_part, property_name):
        try:
            fem_part.addProperty(
                "App::PropertyInteger",
                property_name,
                "MbDFEM",
                "Saved FEMPart results task panel state",
            )
        except Exception:
            pass
    try:
        setattr(fem_part, property_name, int(value))
    except Exception:
        pass


def _default_results_panel_start_state(maximum):
    return 1 if maximum >= 1 else 0


class FEMResultsTaskPanel:
    def __init__(self, results_folder):
        from PySide import QtCore, QtWidgets

        self.results_folder = results_folder
        self.fem_part = owning_fem_part(results_folder)
        self._updating = False
        self._stop_requested = False
        self._playing = False
        self._playback_color_range = None
        self._playback_color_field = ""
        self._suppress_fem_freshness_warning = False

        self._form_widget = QtWidgets.QWidget()
        self._form_widget.setWindowTitle("FEMPart Results")
        self._play_timer = QtCore.QTimer(self._form_widget)
        self._play_timer.setInterval(250)
        self._play_timer.timeout.connect(self._play_next_state)

        layout = QtWidgets.QVBoxLayout(self._form_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header_group = QtWidgets.QGroupBox("Results")
        header_layout = QtWidgets.QVBoxLayout(header_group)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        header_layout.addWidget(self.status_label)
        layout.addWidget(header_group)

        current_group = QtWidgets.QGroupBox("Current State")
        current_layout = QtWidgets.QVBoxLayout(current_group)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        current_layout.addWidget(self.slider)

        frame_layout = QtWidgets.QHBoxLayout()
        self.previous_button = QtWidgets.QToolButton()
        self.previous_button.setText("<")
        self.previous_button.setToolTip("Previous state")
        self.next_button = QtWidgets.QToolButton()
        self.next_button.setText(">")
        self.next_button.setToolTip("Next state")
        frame_layout.addWidget(self.previous_button)
        frame_layout.addWidget(QtWidgets.QLabel("State:"))
        self.state_spin = QtWidgets.QSpinBox()
        frame_layout.addWidget(self.state_spin)
        self.state_count_label = QtWidgets.QLabel()
        frame_layout.addWidget(self.state_count_label)
        frame_layout.addStretch()
        frame_layout.addWidget(QtWidgets.QLabel("Time:"))
        self.time_label = QtWidgets.QLabel()
        frame_layout.addWidget(self.time_label)
        frame_layout.addWidget(self.next_button)
        current_layout.addLayout(frame_layout)
        layout.addWidget(current_group)

        interval_group = QtWidgets.QGroupBox("Play Range")
        interval_layout = QtWidgets.QVBoxLayout(interval_group)

        start_layout = QtWidgets.QHBoxLayout()
        start_layout.addWidget(QtWidgets.QLabel("Start State:"))
        self.start_state_spin = QtWidgets.QSpinBox()
        start_layout.addWidget(self.start_state_spin)
        self.start_state_count_label = QtWidgets.QLabel()
        start_layout.addWidget(self.start_state_count_label)
        start_layout.addStretch()
        start_layout.addWidget(QtWidgets.QLabel("Time:"))
        self.start_time_label = QtWidgets.QLabel()
        start_layout.addWidget(self.start_time_label)
        interval_layout.addLayout(start_layout)

        end_layout = QtWidgets.QHBoxLayout()
        end_layout.addWidget(QtWidgets.QLabel("End State:"))
        self.end_state_spin = QtWidgets.QSpinBox()
        end_layout.addWidget(self.end_state_spin)
        self.end_state_count_label = QtWidgets.QLabel()
        end_layout.addWidget(self.end_state_count_label)
        end_layout.addStretch()
        end_layout.addWidget(QtWidgets.QLabel("Time:"))
        self.end_time_label = QtWidgets.QLabel()
        end_layout.addWidget(self.end_time_label)
        interval_layout.addLayout(end_layout)

        layout.addWidget(interval_group)

        display_group = QtWidgets.QGroupBox("Display")
        display_layout = QtWidgets.QVBoxLayout(display_group)
        self.field_label = QtWidgets.QLabel()
        self.field_label.setObjectName("MbDFEMResultFieldLabel")
        display_layout.addWidget(self.field_label)
        playback_layout = QtWidgets.QHBoxLayout()
        self.play_button = QtWidgets.QPushButton("Play")
        self.stop_playback_button = QtWidgets.QPushButton("Stop")
        playback_layout.addWidget(self.play_button)
        playback_layout.addWidget(self.stop_playback_button)
        display_layout.addLayout(playback_layout)
        layout.addWidget(display_group)
        layout.addStretch(1)

        self.previous_button.clicked.connect(self._previous_state)
        self.next_button.clicked.connect(self._next_state)
        self.slider.valueChanged.connect(self._set_state)
        self.state_spin.valueChanged.connect(self._set_state)
        self.start_state_spin.valueChanged.connect(self._refresh)
        self.end_state_spin.valueChanged.connect(self._refresh)
        self.play_button.clicked.connect(self._play_results)
        self.stop_playback_button.clicked.connect(self._stop_playback)

        pipeline_widgets = self._pipeline_task_widgets()
        self.form = [self._form_widget, *pipeline_widgets] if pipeline_widgets else self._form_widget

        self._configure()
        self._load_panel_state()
        self._refresh()

    def getStandardButtons(self):
        from PySide import QtGui

        return QtGui.QDialogButtonBox.Close

    def accept(self):
        self._stop_solver()
        self._stop_playback()
        self._save_panel_state()
        return True

    def reject(self):
        return self.accept()

    def _panel_state_values(self):
        maximum = max((state_count(self.fem_part) if self.fem_part is not None else 0) - 1, 0)
        default_start = _default_results_panel_start_state(maximum)
        return {
            "current": _clamped_results_panel_state(self.fem_part, "current", 0, maximum)
            if self.fem_part is not None
            else 0,
            "start": _clamped_results_panel_state(self.fem_part, "start", default_start, maximum)
            if self.fem_part is not None
            else 0,
            "end": _clamped_results_panel_state(self.fem_part, "end", maximum, maximum)
            if self.fem_part is not None
            else maximum,
        }

    def _configure(self):
        count = state_count(self.fem_part) if self.fem_part is not None else 0
        maximum = max(count - 1, 0)
        self._updating = True
        try:
            self.slider.setRange(0, maximum)
            self.state_spin.setRange(0, maximum)
            self.start_state_spin.setRange(0, maximum)
            self.end_state_spin.setRange(0, maximum)
        finally:
            self._updating = False
        enabled = self.fem_part is not None and count > 0
        for widget in (
            self.previous_button,
            self.next_button,
            self.slider,
            self.state_spin,
            self.start_state_spin,
            self.end_state_spin,
            self.play_button,
        ):
            widget.setEnabled(enabled)
        self.stop_playback_button.setEnabled(False)

    def _load_panel_state(self):
        self._restore_panel_state(self._panel_state_values(), apply_current=True)

    def _save_panel_state(self):
        if self.fem_part is None:
            return
        for spin_box in (
            self.state_spin,
            self.start_state_spin,
            self.end_state_spin,
        ):
            spin_box.interpretText()

        self._write_panel_state(
            {
                "current": self.state_spin.value(),
                "start": self.start_state_spin.value(),
                "end": self.end_state_spin.value(),
            }
        )

    def _write_panel_state(self, values):
        if self.fem_part is None:
            return
        _set_results_panel_state(self.fem_part, "current", values["current"])
        _set_results_panel_state(self.fem_part, "start", values["start"])
        _set_results_panel_state(self.fem_part, "end", values["end"])

    def _restore_panel_state(self, values, apply_current=False):
        if self.fem_part is None:
            return
        maximum = max(state_count(self.fem_part) - 1, 0)
        current = max(0, min(int(values["current"]), maximum))
        start = max(0, min(int(values["start"]), maximum))
        end = max(0, min(int(values["end"]), maximum))
        if end < start:
            start, end = end, start

        self._updating = True
        try:
            self.slider.setValue(current)
            self.state_spin.setValue(current)
            self.start_state_spin.setValue(start)
            self.end_state_spin.setValue(end)
        finally:
            self._updating = False
        if apply_current and state_count(self.fem_part) > 0:
            self._apply_current_state()
        else:
            self._refresh()

    def _refresh(self, message=None):
        count = state_count(self.fem_part) if self.fem_part is not None else 0
        index = self.state_spin.value()
        if self.fem_part is None:
            self.status_label.setText("No owning FEMPart found.")
        elif count == 0:
            self.status_label.setText("No MbDAssembly state series found.")
        elif message:
            self.status_label.setText(message)
        else:
            solved = len(
                {
                    _result_state_index(result, fallback)
                    for fallback, result in enumerate(_linked_results(self.fem_part))
                }
            )
            self.status_label.setText(f"{self.fem_part.Label}: {solved} / {count} states solved")

        self.state_count_label.setText(f"/ {max(count - 1, 0)}")
        self.time_label.setText(_state_time_text(self.fem_part, index))
        self.start_state_count_label.setText(f"/ {max(count - 1, 0)}")
        self.end_state_count_label.setText(f"/ {max(count - 1, 0)}")
        self.start_time_label.setText(_state_time_text(self.fem_part, self.start_state_spin.value()))
        self.end_time_label.setText(_state_time_text(self.fem_part, self.end_state_spin.value()))
        self._refresh_field_label()

    def _refresh_field_label(self):
        pipeline = getattr(self.fem_part, "visual", None) if self.fem_part is not None else None
        field = _pipeline_field_name(pipeline) if pipeline is not None else _DEFAULT_PIPELINE_FIELD
        self.field_label.setText(f"Field: {_pipeline_field_display_label(field)}" if field else "Field:")

    def _pipeline_for_task_panel(self):
        if self.fem_part is None:
            return None
        pipeline = getattr(self.fem_part, "visual", None)
        if pipeline is not None:
            return pipeline

        results = _linked_results(self.fem_part)
        if not results:
            return None
        return _ensure_visual_pipeline(self.fem_part, results[0])

    def _pipeline_task_widgets(self):
        pipeline = self._pipeline_for_task_panel()
        view_object = getattr(pipeline, "ViewObject", None)
        if view_object is None:
            return []

        widgets = []
        for method_name in (
            "createDisplayTaskWidget",
            "createExtractionTaskWidget",
            "createFramesTaskWidget",
        ):
            try:
                widgets.append(getattr(view_object, method_name)())
            except NotImplementedError:
                pass
            except Exception as exc:
                App.Console.PrintWarning(
                    f"Unable to append FEM pipeline task widget {method_name}: {exc}\n"
                )
        widgets = [widget for widget in widgets if widget is not None]
        for widget in widgets:
            self._connect_pipeline_task_widget(widget)
        return widgets

    def _connect_pipeline_task_widget(self, widget):
        try:
            from PySide import QtWidgets
        except Exception:
            return

        for combo_box in widget.findChildren(QtWidgets.QComboBox):
            if combo_box.objectName() not in ("Field", "VectorMode"):
                continue
            if combo_box.objectName() == "Field":
                _decorate_pipeline_field_combo(combo_box)
                slot = lambda *args, combo_box=combo_box: self._set_pipeline_from_task_panel(
                    combo_box
                )
            else:
                slot = lambda *args: self._set_pipeline_from_task_panel()
            for signal_name in ("activated", "currentIndexChanged"):
                try:
                    signal = getattr(combo_box, signal_name)
                    try:
                        signal[int].connect(slot)
                    except Exception:
                        signal.connect(slot)
                except Exception:
                    pass

    def _refresh_pipeline_task_widgets(self):
        pipeline = getattr(self.fem_part, "visual", None)
        view_object = getattr(pipeline, "ViewObject", None)
        if view_object is None:
            return
        value_range = self._active_playback_color_range(pipeline)
        _refresh_pipeline_fixed_color_range(self.fem_part, pipeline, value_range=value_range)
        _schedule_pipeline_fixed_color_range_refresh(
            self.fem_part,
            pipeline,
            value_range=value_range,
        )

    def _set_pipeline_from_task_panel(self, combo_box=None, *args):
        pipeline = getattr(self.fem_part, "visual", None)
        if pipeline is None:
            return
        view_object = getattr(pipeline, "ViewObject", None)
        if view_object is None:
            return
        try:
            field = ""
            if getattr(combo_box, "objectName", lambda: "")() == "Field":
                field = _pipeline_field_combo_value(combo_box)
            if not field:
                field = _pipeline_field_name(pipeline)
            if field:
                _select_pipeline_field(pipeline, field)
            if getattr(combo_box, "objectName", lambda: "")() == "Field":
                _decorate_pipeline_field_combo(combo_box)
        except Exception:
            pass
        self._playback_color_range = None
        self._playback_color_field = ""
        _refresh_pipeline_fixed_color_range(self.fem_part, pipeline)
        _schedule_pipeline_fixed_color_range_refresh(self.fem_part, pipeline)
        self._refresh_field_label()

    def _active_playback_color_range(self, pipeline):
        if not self._playing:
            return None
        if self._playback_color_field != _pipeline_field_name(pipeline):
            return None
        return self._playback_color_range

    def _active_color_range(self, pipeline):
        playback_range = self._active_playback_color_range(pipeline)
        if playback_range is not None:
            return playback_range
        field = _pipeline_field_name(pipeline) or _DEFAULT_PIPELINE_FIELD
        return _global_pipeline_scalar_range(self.fem_part, field) if field else None

    def _freeze_playback_color_range(self):
        pipeline = getattr(self.fem_part, "visual", None)
        if pipeline is None:
            return
        field = _pipeline_field_name(pipeline)
        self._playback_color_field = field
        self._playback_color_range = (
            _global_pipeline_scalar_range(self.fem_part, field) if field else None
        )

    def _set_state(self, value):
        if self._updating:
            return
        self._updating = True
        try:
            self.slider.setValue(int(value))
            self.state_spin.setValue(int(value))
        finally:
            self._updating = False
        if self.fem_part is not None:
            _set_results_panel_state(self.fem_part, "current", value)
        self._apply_current_state()

    def _previous_state(self):
        self._set_state(max(self.state_spin.value() - 1, self.state_spin.minimum()))

    def _next_state(self):
        self._set_state(min(self.state_spin.value() + 1, self.state_spin.maximum()))

    def _apply_current_state(self):
        if self.fem_part is None:
            return
        try:
            self._show_state(self.state_spin.value())
            self._refresh()
        except Exception as exc:
            App.Console.PrintError(f"{exc}\n")
            self._refresh(str(exc))

    def _times(self):
        assembly = owning_mbd_assembly(self.fem_part) if self.fem_part is not None else None
        times = list(getattr(assembly, "times", [])) if assembly is not None else []
        count = state_count(self.fem_part) if self.fem_part is not None else 0
        if times:
            return [float(value) for value in times[:count]]
        return [float(index) for index in range(count)]

    def _interval_indices(self):
        count = state_count(self.fem_part) if self.fem_part is not None else 0
        if count == 0:
            return []
        start = min(self.start_state_spin.value(), self.end_state_spin.value())
        end = max(self.start_state_spin.value(), self.end_state_spin.value())
        return list(range(start, end + 1))

    def _stop_solver(self):
        self._stop_requested = True

    def _play_results(self):
        indices = self._interval_indices()
        if not indices:
            self._refresh("No states in the selected time interval.")
            return

        self._playing = True
        self.play_button.setEnabled(False)
        self.stop_playback_button.setEnabled(True)
        self._freeze_playback_color_range()
        self._set_state(indices[0])
        self._play_timer.start()

    def _stop_playback(self):
        self._playing = False
        self._playback_color_range = None
        self._playback_color_field = ""
        try:
            self._play_timer.stop()
        except RuntimeError:
            return
        count = state_count(self.fem_part) if self.fem_part is not None else 0
        self.play_button.setEnabled(count > 0)
        self.stop_playback_button.setEnabled(False)

    def _play_next_state(self):
        if not self._playing:
            return

        indices = self._interval_indices()
        if not indices:
            self._stop_playback()
            return

        current = self.state_spin.value()
        try:
            next_position = indices.index(current) + 1
        except ValueError:
            next_position = 0
        if next_position >= len(indices):
            next_position = 0
        self._set_state(indices[next_position])

    def _show_state(self, index):
        current_result = _result_for_state(self.fem_part, index)
        if current_result is not None and not self._suppress_fem_freshness_warning:
            if not self._confirm_warning(
                FreeCADMbDBackend.fem_files_freshness_warning(self.fem_part, index),
                "Stale FEM Files",
            ):
                raise RuntimeError("FEM result display canceled.")

        apply_state(self.fem_part, index)
        pipeline = _ensure_visual_pipeline(self.fem_part, current_result)
        value_range = self._active_color_range(pipeline) if pipeline is not None else None
        if pipeline is not None:
            _refresh_pipeline_fixed_color_range(
                self.fem_part,
                pipeline,
                value_range=value_range,
            )
        self._refresh_pipeline_task_widgets()
        for result in _linked_results(self.fem_part):
            visible = result is current_result
            view_object = getattr(result, "ViewObject", None)
            if view_object is not None:
                try:
                    view_object.Visibility = visible and pipeline is None
                except Exception:
                    pass
            result_mesh = getattr(result, "Mesh", None)
            mesh_view = getattr(result_mesh, "ViewObject", None)
            if mesh_view is not None:
                try:
                    mesh_view.Visibility = visible and pipeline is None
                except Exception:
                    pass
        visual = getattr(self.fem_part, "visual", None)
        visual_view = getattr(visual, "ViewObject", None)
        if visual_view is not None:
            try:
                visual_view.Visibility = pipeline is not None
            except Exception:
                pass
        if pipeline is not None:
            _refresh_pipeline_fixed_color_range(
                self.fem_part,
                pipeline,
                value_range=value_range,
            )
            _schedule_pipeline_fixed_color_range_refresh(
                self.fem_part,
                pipeline,
                value_range=value_range,
            )
            _apply_result_mesh_color_range(self.fem_part, current_result, value_range=value_range)
        else:
            _apply_result_mesh_color_range(self.fem_part, current_result)
        return current_result

    def _run_state(self, index):
        from PySide import QtWidgets

        if self.fem_part is None:
            return False
        try:
            self._refresh(f"Solving state {index}...")
            QtWidgets.QApplication.processEvents()
            result = solve_fem_part_state(self.fem_part, index)
            self._refresh(f"Solved state {index}: {result.Label}")
            return True
        except Exception as exc:
            App.Console.PrintError(f"{exc}\n")
            self._refresh(str(exc))
            return False

    def _set_buttons_enabled(self, enabled):
        count = state_count(self.fem_part) if self.fem_part is not None else 0
        enabled = bool(enabled and self.fem_part is not None and count > 0)
        for widget in (
            self.previous_button,
            self.next_button,
            self.slider,
            self.state_spin,
            self.start_state_spin,
            self.end_state_spin,
            self.play_button,
        ):
            widget.setEnabled(enabled)
        self.stop_playback_button.setEnabled(self._playing)

    def _confirm_warning(self, message, title):
        if not message:
            return True

        App.Console.PrintWarning(message + "\n")
        if not App.GuiUp:
            return True

        from PySide import QtGui

        buttons = QtGui.QMessageBox.Ok | QtGui.QMessageBox.Cancel
        response = QtGui.QMessageBox.warning(None, title, message, buttons, QtGui.QMessageBox.Cancel)
        return response == QtGui.QMessageBox.Ok


def show_results_task_panel(results_folder):
    import FreeCADGui as Gui

    active = Gui.Control.activeDialog()
    if isinstance(active, FEMResultsTaskPanel):
        if active.results_folder == results_folder:
            return active
        Gui.Control.closeDialog()
    elif active is not None:
        Gui.Control.closeDialog()

    panel = FEMResultsTaskPanel(results_folder)
    Gui.Control.showDialog(panel)
    return panel
