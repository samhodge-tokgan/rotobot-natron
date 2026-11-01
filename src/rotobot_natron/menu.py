"""The two Natron menu commands (Rotobot > Import / Export Rotobot JSON...)."""

from __future__ import annotations

import os

import NatronEngine
import NatronGui

from . import model, natron_io


def _app():
    return NatronGui.natron.getActiveInstance()


def import_cmd():
    app = _app()
    path = app.getFilenameDialog(["json"])
    if not path:
        return
    try:
        node = natron_io.import_json(app, path, log=lambda s: None)
    except (ValueError, OSError) as e:
        NatronGui.natron.errorDialog("Rotobot", f"Could not import {os.path.basename(path)}:\n{e}")
        return
    NatronGui.natron.informationDialog(
        "Rotobot", f"Imported {os.path.basename(path)} into {node.getScriptName()}.\n"
                   "Edit points, handles and each shape's Transform; then Rotobot > Export Rotobot JSON.")


def _target(app):
    sel = [n for n in app.getSelectedNodes() if n.getPluginID() == natron_io.PLUGIN_ID]
    if len(sel) == 1:
        return sel[0]
    found = [n for n in app.getChildren() if n.getParam(natron_io.SOURCE_PARAM) is not None]
    return found[0] if len(found) == 1 else None


def export_cmd():
    app = _app()
    node = _target(app)
    if node is None:
        NatronGui.natron.errorDialog("Rotobot", "Select the Roto node that was imported from Rotobot JSON.")
        return
    src = natron_io.source_of(node)
    if not src or not os.path.exists(src):
        src = app.getFilenameDialog(["json"])  # the source moved: ask for it
        if not src:
            return
    out = app.saveFilenameDialog(["json"])
    if not out:
        return
    if not out.endswith(".json"):
        out += ".json"
    if os.path.abspath(out) == os.path.abspath(src):
        NatronGui.natron.errorDialog("Rotobot", "Export to a new file; the source JSON is needed for the next export.")
        return
    try:
        rep = natron_io.export_json(node, out, source_path=src)
    except model.ExportError as e:
        NatronGui.natron.errorDialog("Rotobot", "Not exported:\n" + "\n".join(e.errors[:20]))
        return
    NatronGui.natron.informationDialog("Rotobot", f"Wrote {os.path.basename(out)}\n\n{rep.summary()}")


__all__ = ["import_cmd", "export_cmd", "NatronEngine"]
