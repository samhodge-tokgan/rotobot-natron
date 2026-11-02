"""A one-file Natron launcher for a shot: ``Natron <shot>_natron.py``.

:func:`write` puts ``<shot>_natron.py`` next to ``<shot>.json``. Opening it in
Natron (on the command line, or with NatronRenderer for a batch build) runs
:func:`rotobot_natron.natron_io.open_shot`: the first time it builds
``<shot>.ntp`` from the JSON, after that it opens the saved project, so edits
are kept.

The script uses the ``rotobot_natron`` Natron has already loaded (from
``rotobot-natron install-plugin``); otherwise the first found in the
directories given to :func:`render` (e.g. a copy shipped with the tool that
wrote the JSON), a ``rotobot_natron`` folder beside the script, or anywhere
else on ``sys.path``.

Natron runs a script given on its command line with ``app1`` (and ``app``)
defined and no ``__file__``; the script finds its own directory from
``sys.argv``, falling back to where it was written.

Pure Python: no Natron needed to write a launcher.
"""

from __future__ import annotations

import os
from typing import Iterable

#: The oldest rotobot_natron that has ``natron_io.open_shot``.
MIN_VERSION = "0.2.0"

_TEMPLATE = '''\
# Rotobot shapes for Natron. Open this file with Natron:
#     Natron {script_name}
# The first time it builds {ntp_name} from {json_name}; after that it opens
# {ntp_name}, keeping your edits (delete it to rebuild from the JSON).
# Then Rotobot > Export Rotobot JSON writes the edits back to a new JSON.
# Written by rotobot-natron {version}.
import os
import sys

JSON_NAME = {json_name!r}
NTP_NAME = {ntp_name!r}
SCRIPT_NAME = {script_name!r}
WRITTEN_IN = {written_in!r}
PACKAGE_DIRS = {package_dirs!r}


def _here():
    for a in sys.argv:
        if os.path.basename(a) == SCRIPT_NAME and os.path.isfile(a):
            return os.path.dirname(os.path.abspath(a))
    return WRITTEN_IN


def _fail(msg):
    print("rotobot-natron: " + msg, flush=True)
    try:
        import NatronGui
        NatronGui.natron.errorDialog("Rotobot", msg)
    except Exception:
        pass


def _natron_io(here):
    if "rotobot_natron" not in sys.modules:
        for d in PACKAGE_DIRS + [here]:
            if os.path.isfile(os.path.join(d, "rotobot_natron", "natron_io.py")):
                sys.path.insert(0, d)
                break
    try:
        from rotobot_natron import natron_io
    except ImportError as e:
        _fail("rotobot_natron was not found (%s). Install it with\\n"
              "    pip install rotobot-natron && rotobot-natron install-plugin\\n"
              "and add the printed directory to NATRON_PLUGIN_PATH." % e)
        return None
    if not hasattr(natron_io, "open_shot"):
        _fail("the installed rotobot_natron is too old for this launcher; "
              "upgrade to {min_version} or newer and run rotobot-natron install-plugin again.")
        return None
    return natron_io


def main():
    here = _here()
    src = os.path.join(here, JSON_NAME)
    if not os.path.isfile(src):
        _fail("cannot find " + src + "; keep this script next to its JSON.")
        return
    natron_io = _natron_io(here)
    if natron_io is None:
        return
    app = globals().get("app1") or globals().get("app")
    try:
        natron_io.open_shot(app, src, os.path.join(here, NTP_NAME))
    except Exception as e:
        _fail("could not open %s:\\n%s" % (JSON_NAME, e))
        raise


main()
'''


def _stem(json_path: str, stem: str = "") -> str:
    return stem or os.path.splitext(os.path.basename(json_path))[0]


def script_name(json_path: str, stem: str = "") -> str:
    """``<stem>_natron.py``; the stem defaults to the JSON's."""
    return _stem(json_path, stem) + "_natron.py"


def render(json_path: str, package_dirs: Iterable[str] = (), stem: str = "") -> str:
    """The launcher's text for ``json_path``, which must sit beside it.
    ``package_dirs`` are searched for ``rotobot_natron`` first; ``stem`` names
    the script and the project (``<stem>_natron.py``, ``<stem>.ntp``) and
    defaults to the JSON's."""
    from ._version import __version__

    stem = _stem(json_path, stem)
    return _TEMPLATE.format(script_name=script_name(json_path, stem), json_name=os.path.basename(json_path),
                            ntp_name=stem + ".ntp", version=__version__, min_version=MIN_VERSION,
                            written_in=os.path.dirname(os.path.abspath(json_path)),
                            package_dirs=[str(d) for d in package_dirs])


def write(json_path: str, package_dirs: Iterable[str] = (), stem: str = "") -> str:
    """Write the launcher next to ``json_path``. Returns its path."""
    out = os.path.join(os.path.dirname(os.path.abspath(json_path)), script_name(json_path, stem))
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(json_path, package_dirs, stem))
    return out
