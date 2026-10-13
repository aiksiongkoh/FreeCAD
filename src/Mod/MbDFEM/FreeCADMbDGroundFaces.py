# SPDX-License-Identifier: LGPL-2.1-or-later

"""Ground selected MbDPart faces, retaining the part's assembly and references."""


def selected_faces(selection):
    """Resolve direct and assembly-qualified selections to one part and face names."""
    part = None
    names = []
    for selected in selection:
        if not selected.SubElementNames:
            raise ValueError("Select one or more faces on a single MbDPart.")
        for subname in selected.SubElementNames:
            path, _, name = subname.rstrip(".").rpartition(".")
            candidate = selected.Object.getSubObject(path + ".", retType=1) if path else selected.Object
            if (candidate is None or not candidate.isDerivedFrom("MbDFEM::MbDPart")
                    or not name.startswith("Face") or not name[4:].isdigit()):
                raise ValueError("Select one or more faces on a single MbDPart.")
            if part is not None and candidate != part:
                raise ValueError("Select faces on only one MbDPart at a time.")
            if candidate.Shape.getElement(name).ShapeType != "Face":
                raise ValueError("The selected subelement is not a face.")
            part = candidate
            if name not in names:
                names.append(name)
    if part is None:
        raise ValueError("Select one or more faces on a single MbDPart.")
    return part, names


def ground_faces(part, names):
    """Convert and ground a part in one undoable transaction."""
    import MbDFEM

    names = list(dict.fromkeys(names))
    if not names or any(not name.startswith("Face") or not name[4:].isdigit()
                        for name in names):
        raise ValueError("Select one or more faces on a single MbDPart.")
    for name in names:
        if part.Shape.getElement(name).ShapeType != "Face":
            raise ValueError("The selected subelement is not a face.")
    document = part.Document
    # View properties must be captured before conversion removes the original.
    view_properties = {}
    if part.ViewObject is not None:
        view_properties = {name: getattr(part.ViewObject, name)
                           for name in part.ViewObject.PropertiesList
                           if name not in ("RootNode", "Proxy")}
    document.openTransaction("Ground Faces")
    try:
        ground = MbDFEM.convertToGroundPart(part)
        for name, value in view_properties.items():
            if name in ground.ViewObject.PropertiesList:
                try:
                    setattr(ground.ViewObject, name, value)
                except (AttributeError, TypeError, RuntimeError):
                    pass  # Some view properties are read-only.
        existing = [name for object_, subnames in ground.groundFaces
                    if object_ == ground for name in subnames]
        ground.groundFaces = [(ground, list(dict.fromkeys(existing + names)))]
        document.recompute()
        document.commitTransaction()
        return ground
    except Exception:
        document.abortTransaction()
        raise


class GroundFacesCommand:
    def GetResources(self):
        return {"MenuText": "Ground Faces",
                "ToolTip": "Ground selected MbDPart faces and move the part to FixedParts"}

    def IsActive(self):
        import FreeCAD as App
        import FreeCADGui as Gui

        if App.ActiveDocument is None:
            return False
        try:
            part, _ = selected_faces(Gui.Selection.getSelectionEx(App.ActiveDocument.Name, 0, True))
            return any(obj.isDerivedFrom("MbDFEM::MbDAssembly")
                       and (part in obj.parts or part in obj.fixedparts)
                       for obj in part.Document.Objects)
        except (ValueError, RuntimeError):
            return False

    def Activated(self):
        import FreeCAD as App
        import FreeCADGui as Gui

        try:
            part, names = selected_faces(Gui.Selection.getSelectionEx(App.ActiveDocument.Name, 0, True))
            ground = ground_faces(part, names)
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(ground)
        except Exception as exc:
            App.Console.PrintError(f"Ground Faces: {exc}\n")
