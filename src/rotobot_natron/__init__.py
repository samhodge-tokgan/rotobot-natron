"""Edit Rotobot-Next ``lozenge_bezier_anim`` JSON in Natron as native Roto shapes.

The package is pure Python except :mod:`rotobot_natron.natron_io`, which is the
only module that imports ``NatronEngine``; everything else runs (and is tested)
outside Natron.
"""

from ._version import __version__

__all__ = ["__version__"]
