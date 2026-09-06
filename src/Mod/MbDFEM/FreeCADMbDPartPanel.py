# SPDX-License-Identifier: LGPL-2.1-or-later

"""Task panel for MbDPart initial velocity controls."""

import FreeCAD as App
import FreeCADGui as Gui


def is_mbd_part(obj):
    try:
        return obj is not None and obj.isDerivedFrom("MbDFEM::MbDPart")
    except Exception:
        return False


def _format_property_float(value):
    mantissa, exponent = f"{float(value):.16e}".split("e")
    mantissa = mantissa.rstrip("0").rstrip(".")
    if "." not in mantissa:
        mantissa += ".0"
    return f"{mantissa}e{exponent}"


def _float_from_text(field):
    text = field.text().strip()
    decimal_point = field.locale().decimalPoint()
    if decimal_point != ".":
        text = text.replace(decimal_point, ".")
    return float(text)


class PartTaskPanel:
    """Task-tab controls for an MbDPart."""

    def __init__(self, part):
        from PySide import QtWidgets

        if not is_mbd_part(part):
            raise TypeError("PartTaskPanel requires an MbDPart")

        self.part = part
        self._original_values = self._values()

        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("MbDPart")

        layout = QtWidgets.QVBoxLayout(self.form)

        velocity_group = QtWidgets.QGroupBox("Velocity")
        velocity_layout = QtWidgets.QFormLayout(velocity_group)
        omega_group = QtWidgets.QGroupBox("Omega")
        omega_layout = QtWidgets.QFormLayout(omega_group)

        self.velocity_x = self._double_line_edit(part.velocity.x, -1.0e12, 1.0e12)
        self.velocity_y = self._double_line_edit(part.velocity.y, -1.0e12, 1.0e12)
        self.velocity_z = self._double_line_edit(part.velocity.z, -1.0e12, 1.0e12)
        self.omega_x = self._double_line_edit(part.omega.x, -1.0e12, 1.0e12)
        self.omega_y = self._double_line_edit(part.omega.y, -1.0e12, 1.0e12)
        self.omega_z = self._double_line_edit(part.omega.z, -1.0e12, 1.0e12)

        self._fields = [
            self.velocity_x,
            self.velocity_y,
            self.velocity_z,
            self.omega_x,
            self.omega_y,
            self.omega_z,
        ]

        velocity_layout.addRow("x", self.velocity_x)
        velocity_layout.addRow("y", self.velocity_y)
        velocity_layout.addRow("z", self.velocity_z)
        omega_layout.addRow("x", self.omega_x)
        omega_layout.addRow("y", self.omega_y)
        omega_layout.addRow("z", self.omega_z)

        layout.addWidget(velocity_group)
        layout.addWidget(omega_group)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    @staticmethod
    def _double_line_edit(value, minimum, maximum):
        from PySide import QtGui, QtWidgets

        field = QtWidgets.QLineEdit(_format_property_float(value))
        validator = QtGui.QDoubleValidator(minimum, maximum, 16, field)
        validator.setNotation(QtGui.QDoubleValidator.ScientificNotation)
        field.setValidator(validator)
        return field

    def getStandardButtons(self):
        from PySide import QtGui

        return QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel

    def accept(self):
        if not self._apply_values():
            return False

        Gui.Control.closeDialog()
        return True

    def reject(self):
        self._restore_values(self._original_values)
        Gui.Control.closeDialog()
        return True

    def _apply_values(self):
        invalid_fields = [field for field in self._fields if not field.hasAcceptableInput()]
        if invalid_fields:
            self._set_status("Enter valid velocity and omega values.")
            return False

        document = self.part.Document
        if document is None:
            return False

        document.openTransaction("Edit MbDPart")
        try:
            self.part.velocity = App.Vector(
                _float_from_text(self.velocity_x),
                _float_from_text(self.velocity_y),
                _float_from_text(self.velocity_z),
            )
            self.part.omega = App.Vector(
                _float_from_text(self.omega_x),
                _float_from_text(self.omega_y),
                _float_from_text(self.omega_z),
            )
            document.commitTransaction()
        except Exception:
            document.abortTransaction()
            raise

        document.recompute()
        return True

    def _values(self):
        return {
            "velocity": App.Vector(self.part.velocity),
            "omega": App.Vector(self.part.omega),
        }

    def _restore_values(self, values):
        self.part.velocity = values["velocity"]
        self.part.omega = values["omega"]

    def _set_status(self, message):
        self.status_label.setText(message)
        App.Console.PrintMessage(message + "\n")


def show_part_task_panel(part):
    if not is_mbd_part(part):
        App.Console.PrintError("Part task panel requires an MbDPart.\n")
        return None

    active = Gui.Control.activeDialog()
    if isinstance(active, PartTaskPanel):
        if active.part == part:
            return active
        Gui.Control.closeDialog()
    elif active is not None:
        Gui.Control.closeDialog()

    panel = PartTaskPanel(part)
    Gui.Control.showDialog(panel)
    return panel
