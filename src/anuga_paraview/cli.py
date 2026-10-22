"""anuga-paraview: start ParaView with the .sww reader loaded.

    anuga-paraview                  # open .sww files with File > Open
    anuga-paraview run.sww          # open a file with a ready-made view
    anuga-paraview --plugin-path    # the directory to put on PV_PLUGIN_PATH

It runs the paraview on the PATH, or the one given by --paraview or
$PARAVIEW.
"""

import argparse
import os
import shutil
import subprocess
import sys

from anuga_paraview import PLUGIN_DIR, VIEW_SCRIPT, __version__


def paraview_command(paraview, filename=None, environ=None):
    """The command line and environment that start ParaView with the
    reader, and with a ready-made view of filename if given."""
    env = dict(os.environ if environ is None else environ)
    old = env.get('PV_PLUGIN_PATH')
    env['PV_PLUGIN_PATH'] = PLUGIN_DIR + (os.pathsep + old if old else '')
    # ParaView can hang at startup under Wayland; run it through XWayland.
    if env.get('XDG_SESSION_TYPE') == 'wayland' and 'QT_QPA_PLATFORM' not in env:
        env['QT_QPA_PLATFORM'] = 'xcb'
    command = [paraview]
    if filename is not None:
        env['ANUGA_SWW_FILE'] = os.path.abspath(filename)
        command.append('--script=' + VIEW_SCRIPT)
    return command, env


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='anuga-paraview',
        description='Start ParaView with the ANUGA .sww reader loaded.')
    parser.add_argument('sww', nargs='?', help='a .sww file to open with a ready-made view')
    parser.add_argument('--paraview', default=os.environ.get('PARAVIEW', 'paraview'),
                        help='the ParaView to run (default: $PARAVIEW, or paraview on the PATH)')
    parser.add_argument('--plugin-path', action='store_true',
                        help='print the directory to put on PV_PLUGIN_PATH, and exit')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)

    if args.plugin_path:
        print(PLUGIN_DIR)
        return 0
    if args.sww is not None and not os.path.isfile(args.sww):
        parser.error('no such file: %s' % args.sww)
    paraview = shutil.which(args.paraview)
    if paraview is None:
        parser.error('cannot find %s; install ParaView (conda install -c conda-forge '
                     'paraview netcdf4), or give its path with --paraview' % args.paraview)

    command, env = paraview_command(paraview, args.sww)
    return subprocess.call(command, env=env)


if __name__ == '__main__':
    sys.exit(main())
