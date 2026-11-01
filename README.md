# rotobot-natron

Open Rotobot-Next shape files (`lozenge_bezier_anim` JSON) in [Natron](https://natrongithub.github.io/) as native, editable Roto shapes. Then export your edits back to the same JSON, so every other importer (Silhouette, Nuke, After Effects) picks them up.

* Each JSON object becomes one closed Bezier, under layers per person and body part.
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

* **Rotobot → Import Rotobot JSON…** creates a `Rotobot` Roto node. It also sets the frame range, the frame rate, and the project format when Natron has a matching built-in format. Connect your plate to its Bg input to see the shapes over it.
* Edit points, handles and each shape's Transform.
* **Rotobot → Export Rotobot JSON…** writes a new JSON next to the source.

`rotobot-natron check FILE.json` reports whether a file can be opened.

### Large shots

In Natron 2.5, setting one control point through the Python API costs time in proportion to the shape's points times its keyframes. Building a dense shot point by point therefore slows down with the square of both.

`natron_io.import_json_fast` avoids this:
1. It builds each shape with a single key.
2. It saves the project and writes every frame's keys straight into the saved file, using the same Smooth derivatives the API would store.
3. It reloads the project.

On a 4096×2160 test shot with 69 shapes, 3,038 points per frame and 120 frames, the import took 43 s this way. The API-only path was still running after 17 minutes. Natron's project files are large: that shot saves as 664 MB.

## Natron notes

* Natron 2.x renders Roto shapes **without antialiasing**, into an 8-bit mask per shape. Its built-in Roto motion blur is compiled out of every 2.x release. For a motion-blurred matte, put a TimeBlur node after the Roto node.
* Shape keys interpolate as Natron "Smooth" (clamped Catmull-Rom). Every source frame is keyed, so values on frames are exact.
* The per-shape "extra matrix" is not reachable from Python, so a projective camera move is folded into the points, not the transform.

## Tests

```
pip install -e '.[dev]'; pytest -q                     # pure Python
RN_SRC=$PWD/src RN_JSON=shapes.json RN_OUT=/tmp/rt \
  NatronRenderer -t tests/natron/roundtrip.py </dev/null   # inside Natron
```

MIT licence.
