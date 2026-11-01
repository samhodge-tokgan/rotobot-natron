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
        nodes = natron_io.import_json(app, path, log=lambda s: None)
    except (ValueError, OSError) as e:
        NatronGui.natron.errorDialog("Rotobot", f"Could not import {os.path.basename(path)}:\n{e}")
        return
    NatronGui.natron.informationDialog(
        "Rotobot", f"Imported {os.path.basename(path)} into {', '.join(n.getScriptName() for n in nodes)}.\n"
                   "Connect the plate to the first node's Bg input; the last node is the combined matte.\n"
                   "Edit points, handles and each shape's Transform; then Rotobot > Export Rotobot JSON.")


def _targets(app):
    """The nodes of one import: those sharing the selected node's source, or
    every Rotobot node when they all come from one source."""
    sel = [n for n in app.getSelectedNodes() if n.getParam(natron_io.SOURCE_PARAM) is not None]
    if sel:
        return natron_io.rotobot_nodes(app, natron_io.source_of(sel[0]))
    found = natron_io.rotobot_nodes(app)
    return found if len({natron_io.source_of(n) for n in found}) == 1 else []


def export_cmd():
    app = _app()
    nodes = _targets(app)
    if not nodes:
        NatronGui.natron.errorDialog("Rotobot", "Select one of the Roto nodes that were imported from Rotobot JSON.")
        return
    src = natron_io.source_of(nodes[0])
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
        rep = natron_io.export_json(nodes, out, source_path=src)
    except model.ExportError as e:
        NatronGui.natron.errorDialog("Rotobot", "Not exported:\n" + "\n".join(e.errors[:20]))
        return
    NatronGui.natron.informationDialog("Rotobot", f"Wrote {os.path.basename(out)}\n\n{rep.summary()}")


__all__ = ["import_cmd", "export_cmd", "NatronEngine"]
