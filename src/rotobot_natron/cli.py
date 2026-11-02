"""``rotobot-natron``: install the Natron plugin, check a JSON file.

    rotobot-natron install-plugin [--dest DIR]
    rotobot-natron check FILE.json
    rotobot-natron launcher FILE.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from . import _version, launcher, model

PKG = Path(__file__).resolve().parent


def default_dest() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "rotobot-natron" / "plugin"
    return Path.home() / ".local" / "share" / "rotobot-natron" / "plugin"


def install_plugin(dest: Path) -> Path:
    """Copy the start-up hooks and the package into ``dest``, a directory to put
    on NATRON_PLUGIN_PATH. Natron's Python ignores user site-packages, so the
    package travels with the hooks."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("init.py", "initGui.py"):
        shutil.copy2(PKG / "plugin" / name, dest / name)
    target = dest / "rotobot_natron"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(PKG, target, ignore=shutil.ignore_patterns("__pycache__", "plugin"))
    return dest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="rotobot-natron", description=__doc__.splitlines()[0])
    ap.add_argument("--version", action="version", version=_version.__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ip = sub.add_parser("install-plugin", help="install the Natron menu plugin")
    ip.add_argument("--dest", type=Path, default=None, help=f"plugin directory (default {default_dest()})")
    cp = sub.add_parser("check", help="check that a Rotobot JSON file can be opened in Natron")
    cp.add_argument("file", type=Path)
    lp = sub.add_parser("launcher", help="write FILE_natron.py, which opens the shot when run with Natron")
    lp.add_argument("file", type=Path)
    lp.add_argument("--package-dir", action="append", default=[],
                    help="a directory holding rotobot_natron for the launcher to try first (repeatable)")
    lp.add_argument("--stem", default="", help="name the script STEM_natron.py and the project STEM.ntp")
    a = ap.parse_args(argv)

    if a.cmd == "install-plugin":
        dest = install_plugin(a.dest or default_dest())
        sep = ";"  # Natron splits NATRON_PLUGIN_PATH on ';' on every platform
        print(f"Installed to {dest}\nAdd it to NATRON_PLUGIN_PATH (entries separated by '{sep}'), e.g.\n"
              + (f'  setx NATRON_PLUGIN_PATH "{dest}"' if sys.platform == "win32"
                 else f'  export NATRON_PLUGIN_PATH="{dest}"')
              + "\nthen restart Natron: the Rotobot menu has Import / Export Rotobot JSON.")
        return 0
    if a.cmd == "check":
        try:
            raw = json.loads(a.file.read_text())
        except (OSError, ValueError) as e:
            print(f"{a.file}: {e}", file=sys.stderr)
            return 2
        errs = model.check_document(raw)
        for e in errs:
            print(f"{a.file}: {e}", file=sys.stderr)
        if not errs:
            plan = model.build_plan(raw)
            print(f"{a.file}: OK, {len(plan.shapes)} shapes, Natron frames {plan.first}-{plan.last}")
        return 1 if errs else 0
    if a.cmd == "launcher":
        out = launcher.write(str(a.file), a.package_dir, a.stem)
        print(f"Wrote {out}\nOpen it with Natron: Natron {out}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
