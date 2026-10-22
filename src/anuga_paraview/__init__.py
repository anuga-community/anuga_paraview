"""View ANUGA .sww files in ParaView, and in a web browser.

The ParaView reader is ``plugin/sww_reader.py``, alone in its directory
because ParaView loads every ``.py`` file in a ``PV_PLUGIN_PATH`` directory
as a plugin.
"""

import os

__version__ = '0.1.0'

HERE = os.path.dirname(os.path.abspath(__file__))

# The directory to put on PV_PLUGIN_PATH, and the plugin in it.
PLUGIN_DIR = os.path.join(HERE, 'plugin')
PLUGIN = os.path.join(PLUGIN_DIR, 'sww_reader.py')

# The ParaView script that sets up a ready-made view of a file.
VIEW_SCRIPT = os.path.join(HERE, 'scripts', 'view_sww.py')
