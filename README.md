# rotobot-natron

Open Rotobot-Next shape files (`lozenge_bezier_anim` JSON) in [Natron](https://natrongithub.github.io/) as native, editable Roto shapes. Then export your edits back to the same JSON, so every other importer (Silhouette, Nuke, After Effects) picks them up.

* Each JSON object becomes one closed Bezier, in layers per body part, with one Roto node per person (`Rotobot_p0`, `Rotobot_p1`, ...) chained through their Bg inputs; the last node is the combined matte.
* Each shape's **Transform** (translate and rotate) carries the part's motion, and its points sit in that part's local space. Moving a shape is a transform edit, not 120 frames of point edits.
* **Export** writes only the frames you changed into a copy of the original file; every other key in the file is kept.
  * An unedited round trip gives back the identical document.
  * Objects that carry B-spline control points (`cps`) stay B-splines. An edit that is no longer an exact B-spline is refit with the same number of control points, and the deviation is reported.
* **Export refuses changes it can't map back**, and says what is wrong: a shape added or deleted, or points added or removed.

Requires Natron 2.5 (tested with 2.5.0 on Linux). The package is plain Python with no dependencies.

## Install

```
pip install rotobot-natron
rotobot-natron install-plugin
```

Then add the printed directory to `NATRON_PLUGIN_PATH` and restart Natron. Natron's own Python does not see your site-packages, so the plugin directory carries a copy of the package.

## Use

* **Rotobot → Import Rotobot JSON…** creates the Roto nodes. It also sets the frame range, the frame rate, and the project format when Natron has a built-in format of the plate's size; otherwise a transparent canvas of that size feeds the first node. Connect your plate to the first node's Bg input to see the shapes over it.
* Edit points, handles and each shape's Transform.
* **Rotobot → Export Rotobot JSON…** writes a new JSON next to the source.

`rotobot-natron check FILE.json` reports whether a file can be opened.

If a menu closes before you can pick an item (seen with Natron 2.5's Qt4 on
GNOME), press and hold on *Rotobot*, drag to the item, then release, or run
the same commands from the Script Editor:

```
rotobot_natron.menu.import_cmd()
rotobot_natron.menu.export_cmd()
```

Errors from the menu commands are printed in the Script Editor.

If Natron 2.5 crashes at start-up on a Linux desktop with an NVIDIA driver, start
it with Mesa's OpenGL instead (the viewer then draws in software):

```
__GLX_VENDOR_LIBRARY_NAME=mesa /path/to/Natron
```

### Large shots

In Natron 2.5, setting one control point through the Python API costs time in proportion to the shape's points times its keyframes. Building a dense shot point by point therefore slows down with the square of both.

`natron_io.import_json_fast` avoids this:
1. It builds each shape with a single key.
2. It saves the project and writes every frame's keys straight into the saved file, using the same Smooth derivatives the API would store.
3. It reloads the project.

On a 4096×2160 test shot with 69 shapes, 3,038 points per frame and 120 frames, the import took 43 s this way. The API-only path was still running after 17 minutes. Natron's project files are large: that shot saves as 664 MB.

## Natron notes

* A Roto node renders at most about 64 shapes in Natron 2.5: when its internal
  Merge fills up more are chained, but the node outputs the first one. Hence
  one node per person.
* The animated "activated" switch is ignored when rendering, so visibility is
  keyed on each shape's opacity, stepped just before the frame.

* Natron 2.x renders Roto shapes **without antialiasing**, into an 8-bit mask per shape. Its built-in Roto motion blur is compiled out of every 2.x release. For a motion-blurred matte, put a TimeBlur node after the Roto node.
* Shape keys interpolate as Natron "Smooth" (clamped Catmull-Rom). Every source frame is keyed, so values on frames are exact.
* A point whose two handles are not in line with it (a kink) comes back from a
  saved Natron 2.5 project with its handles re-aligned. Rotobot output never
  has kinks; a kink drawn in Natron is exported as Natron keeps it.
* The per-shape "extra matrix" is not reachable from Python, so a projective camera move is folded into the points, not the transform.

## Tests

```
pip install -e '.[dev]'; pytest -q                     # pure Python
RN_SRC=$PWD/src RN_JSON=shapes.json RN_OUT=/tmp/rt \
  NatronRenderer -t tests/natron/roundtrip.py </dev/null   # inside Natron
```

MIT licence.
