"""Natron GUI start-up hook installed by ``rotobot-natron install-plugin``.

Natron runs every ``initGui.py`` it finds on ``NATRON_PLUGIN_PATH`` when the
GUI starts; the directory is on ``sys.path`` too, so the package beside this
file imports. Menu commands are looked up by name in ``__main__``.
"""

import NatronGui

import rotobot_natron.menu  # noqa: F401  (the menu commands below resolve through it)

NatronGui.natron.addMenuCommand("Rotobot/Import Rotobot JSON...", "rotobot_natron.menu.import_cmd")
NatronGui.natron.addMenuCommand("Rotobot/Export Rotobot JSON...", "rotobot_natron.menu.export_cmd")
