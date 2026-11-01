"""Build a demo project: plate Read -> Rotobot Roto -> Viewer.

    RN_SRC=src RN_JSON=shapes.json RN_PLATE=/path/clip.####.jpg RN_OUT=dir \
        NatronRenderer -t tests/natron/demo_project.py </dev/null
"""

import os
import sys

sys.path.insert(0, os.environ["RN_SRC"])

from rotobot_natron import natron_io  # noqa: E402

app = app1  # noqa: F821
out = os.environ["RN_OUT"]
os.makedirs(out, exist_ok=True)
app, roto = natron_io.import_json_fast(app, os.environ["RN_JSON"], os.path.join(out, "demo.ntp"))
fmt = app.getProjectParam("outputFormat")
print("format", fmt.getOption(fmt.getValue()), flush=True)
if os.environ.get("RN_PLATE"):
    read = app.createNode("fr.inria.built-in.Read")
    read.getParam("filename").setValue(os.environ["RN_PLATE"])
    fr = app.getProjectParam("frameRange")
    a, b = int(fr.getValue(0)), int(fr.getValue(1))
    read.getParam("firstFrame").setValue(a)
    read.getParam("lastFrame").setValue(b)
    read.getParam("startingTime").setValue(a)
    roto.connectInput(0, read)
    read.setPosition(0, -150)
viewer = app.createNode("fr.inria.built-in.Viewer")  # None headless: the GUI adds one
if viewer is not None:
    viewer.connectInput(0, roto)
app.saveProjectAs(os.path.join(out, "demo.ntp"))
print("saved", os.path.join(out, "demo.ntp"), flush=True)
sys.stdout.flush()
os._exit(0)
