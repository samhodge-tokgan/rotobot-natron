"""The launcher script, run outside Natron against a stand-in package."""

import json
import os
import subprocess
import sys
import textwrap

from rotobot_natron import cli, launcher

STUB = '''
import json, os
def open_shot(app, json_path, project_path=None, log=print):
    with open(os.path.join(os.path.dirname(json_path), "opened.json"), "w") as f:
        json.dump({"app": app, "json": json_path, "ntp": project_path, "file": __file__}, f)
'''


def _stub(root):
    pkg = root / "rotobot_natron"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "natron_io.py").write_text(STUB)
    return root


def _run(script, cwd):
    # -S: no site-packages, as in Natron; app1 stands in for the one Natron defines.
    code = "app1 = 'APP'\n" + script.read_text()
    p = subprocess.run([sys.executable, "-S", "-c", code, str(script)], cwd=cwd, capture_output=True, text=True)
    return p


def test_render_compiles_and_names_the_shot(tmp_path):
    text = launcher.render(str(tmp_path / "r123.json"), ["/opt/x"])
    compile(text, "r123_natron.py", "exec")
    assert "JSON_NAME = 'r123.json'" in text and "SCRIPT_NAME = 'r123_natron.py'" in text
    assert "PACKAGE_DIRS = ['/opt/x']" in text and "r123.ntp" in text


def test_launcher_opens_the_shot_with_the_given_package(tmp_path):
    shot = tmp_path / "shot"
    shot.mkdir()
    (shot / "s.json").write_text("{}")
    pkgdir = _stub(tmp_path / "pkg")
    script = launcher.write(str(shot / "s.json"), [str(pkgdir)])
    p = _run(shot / os.path.basename(script), cwd=tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    got = json.loads((shot / "opened.json").read_text())
    assert got["app"] == "APP" and got["json"] == str(shot / "s.json")
    assert got["file"].startswith(str(pkgdir))


def test_launcher_follows_a_moved_shot_and_finds_a_package_beside_it(tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    (old / "s.json").write_text("{}")
    launcher.write(str(old / "s.json"), ["/nonexistent"])
    new = tmp_path / "new"
    old.rename(new)
    _stub(new)
    p = _run(new / "s_natron.py", cwd=tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads((new / "opened.json").read_text())["json"] == str(new / "s.json")


def test_launcher_without_the_package_says_how_to_install_it(tmp_path):
    (tmp_path / "s.json").write_text("{}")
    launcher.write(str(tmp_path / "s.json"))
    p = _run(tmp_path / "s_natron.py", cwd=tmp_path)
    assert "pip install rotobot-natron" in p.stdout
    assert not (tmp_path / "opened.json").exists()


def test_cli_writes_the_launcher(tmp_path, capsys):
    (tmp_path / "s.json").write_text("{}")
    assert cli.main(["launcher", str(tmp_path / "s.json"), "--package-dir", "/opt/x"]) == 0
    assert "PACKAGE_DIRS = ['/opt/x']" in (tmp_path / "s_natron.py").read_text()


def test_stem_names_the_script_and_the_project(tmp_path):
    (tmp_path / "plates__123.json").write_text("{}")
    _stub(tmp_path / "pkg")
    script = launcher.write(str(tmp_path / "plates__123.json"), [str(tmp_path / "pkg")], stem="shot_010")
    assert os.path.basename(script) == "shot_010_natron.py"
    p = _run(tmp_path / "shot_010_natron.py", cwd=tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    got = json.loads((tmp_path / "opened.json").read_text())
    assert got["json"] == str(tmp_path / "plates__123.json") and got["ntp"] == str(tmp_path / "shot_010.ntp")
