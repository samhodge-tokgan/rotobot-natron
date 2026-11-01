"""Natron start-up hook installed by ``rotobot-natron install-plugin``.

Runs in the GUI and in NatronRenderer. Nothing to register for batch use: a
script can ``from rotobot_natron import natron_io`` directly, because Natron
puts this directory on ``sys.path``.
"""
