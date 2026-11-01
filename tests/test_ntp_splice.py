import pytest

from rotobot_natron import ntp_splice

# One curve exactly as Natron 2.5.0 saved it after an in-order build through
# the Python API (times 1001..1006, Smooth keys).
TIMES = [1001.0, 1002.0, 1003.0, 1004.0, 1005.0, 1006.0]
VALUES = [1.56531262069940567e+02, 1.55681123664511830e+02, 1.54914845548463376e+02,
          1.53959635670887110e+02, 1.52875705417884433e+02, 1.51937403719748630e+02]
NATRON = [(0.0, -8.50138405428737087e-01), (-8.08208260738595641e-01, -8.08208260738595641e-01),
          (-8.60743996812360024e-01, -8.60743996812360024e-01), (-1.01957006528947147e+00, -1.01957006528947147e+00),
          (-1.01111597556923982e+00, -1.01111597556923982e+00), (-1.40745254720371804e+00, 0.0)]


def test_derivatives_match_what_natron_saved():
    for got, want in zip(ntp_splice.smooth_derivatives(TIMES, VALUES), NATRON):
        assert got == pytest.approx(want, abs=1e-12)


def test_extremum_is_flat_and_short_curves():
    d = ntp_splice.smooth_derivatives([1, 2, 3], [0.0, 5.0, 1.0])
    assert d[1] == (0.0, 0.0)
    assert ntp_splice.smooth_derivatives([4], [2.0]) == [(0.0, 0.0)]
    assert ntp_splice.smooth_derivatives([1, 3], [0.0, 4.0]) == [(0.0, 2.0), (2.0, 0.0)]


def _cp(tag, first):
    curves = []
    for c in ("X", "Y", "Left_X", "Left_Y", "Right_X", "Right_Y"):
        open_set = '<KeyFrameSet class_id="9" tracking_level="0" version="0">' if first and c == "X" else "<KeyFrameSet>"
        item = '<item class_id="10" tracking_level="0" version="0">' if first and c == "X" else "<item>"
        curves.append(f"<{c}>0</{c}>\n<{c}_animation>\n\t{open_set}\n\t\t<count>1</count>\n\t\t<item_version>0</item_version>\n"
                      f"\t\t{item}\n\t\t\t<Time>1</Time><Value>0</Value>\n\t\t</item>\n\t</KeyFrameSet>\n</{c}_animation>\n")
    return f"<{tag}>\n" + "".join(curves) + f"<Broken>0</Broken>\n</{tag}>\n"


def test_splice_rewrites_every_curve_and_keeps_class_ids():
    text = ("<Item><Name>other</Name><NumPoints>1</NumPoints>" + _cp("CP", True) + _cp("FP", False) + "</Item>"
            "<Item><Name>p0_head</Name><knob><Name>translate</Name></knob><NumPoints>2</NumPoints>"
            + _cp("CP", False) + _cp("FP", False) + _cp("CP", False) + _cp("FP", False) + "</Item>")
    frames = [[(1, 2, 3, 4, 5, 6), (7, 8, 9, 10, 11, 12)], [(2, 3, 4, 5, 6, 7), (8, 9, 10, 11, 12, 13)]]
    out, n = ntp_splice.splice(text, {"p0_head": ([1.0, 2.0], frames)})
    assert n == 1
    assert out.count("<count>2</count>") == 2 * 2 * 6  # 2 points x (CP, FP) x 6 curves
    assert out.count("<count>1</count>") == 2 * 6  # "other" untouched
    assert out.count('class_id="9"') == 1 and out.count('class_id="10"') == 1
    assert "<Value>1.10000000000000000e+01</Value>" in out  # point 1 right_x at t=1
    with pytest.raises(ValueError):
        ntp_splice.splice(text, {"p0_head": ([1.0], [[(0,) * 6]])})
