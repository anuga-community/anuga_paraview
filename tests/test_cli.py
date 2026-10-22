"""The anuga-paraview launcher."""

import os
import stat
import sys

import pytest

from anuga_paraview import PLUGIN, PLUGIN_DIR, VIEW_SCRIPT, cli

from conftest import NO_MOMENTUM


def test_the_plugin_is_alone_in_its_directory():
    # ParaView loads every .py file on PV_PLUGIN_PATH as a plugin.
    assert os.path.isfile(PLUGIN)
    assert [f for f in os.listdir(PLUGIN_DIR) if f.endswith('.py')] == ['sww_reader.py']
    assert os.path.isfile(VIEW_SCRIPT)


def test_plugin_path_is_prepended():
    _, env = cli.paraview_command('paraview', environ={'PV_PLUGIN_PATH': '/other'})
    assert env['PV_PLUGIN_PATH'] == PLUGIN_DIR + os.pathsep + '/other'
    _, env = cli.paraview_command('paraview', environ={})
    assert env['PV_PLUGIN_PATH'] == PLUGIN_DIR


def test_a_file_opens_with_the_view_script():
    command, env = cli.paraview_command('paraview', 'data/cairns.sww', environ={})
    assert command == ['paraview', '--script=' + VIEW_SCRIPT]
    assert env['ANUGA_SWW_FILE'] == os.path.abspath('data/cairns.sww')
    command, env = cli.paraview_command('paraview', environ={})
    assert command == ['paraview'] and 'ANUGA_SWW_FILE' not in env


def test_wayland_runs_on_x11_unless_told_otherwise():
    _, env = cli.paraview_command('paraview', environ={'XDG_SESSION_TYPE': 'wayland'})
    assert env['QT_QPA_PLATFORM'] == 'xcb'
    _, env = cli.paraview_command(
        'paraview', environ={'XDG_SESSION_TYPE': 'wayland', 'QT_QPA_PLATFORM': 'wayland'})
    assert env['QT_QPA_PLATFORM'] == 'wayland'
    _, env = cli.paraview_command('paraview', environ={'XDG_SESSION_TYPE': 'x11'})
    assert 'QT_QPA_PLATFORM' not in env


def test_plugin_path_option(capsys):
    assert cli.main(['--plugin-path']) == 0
    assert capsys.readouterr().out.strip() == PLUGIN_DIR


def test_errors(capsys):
    with pytest.raises(SystemExit):
        cli.main(['no-such-file.sww'])
    assert 'no such file' in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main(['--paraview', 'no-such-paraview', NO_MOMENTUM])
    assert 'cannot find no-such-paraview' in capsys.readouterr().err


@pytest.mark.skipif(sys.platform == 'win32', reason='uses a shell script as ParaView')
def test_paraview_is_started(tmp_path):
    out = tmp_path / 'args'
    fake = tmp_path / 'paraview'
    fake.write_text('#!/bin/sh\necho "$@" "$PV_PLUGIN_PATH" "$ANUGA_SWW_FILE" > %s\nexit 3\n' % out)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    assert cli.main(['--paraview', str(fake), NO_MOMENTUM]) == 3
    assert out.read_text().split() == ['--script=' + VIEW_SCRIPT, PLUGIN_DIR, NO_MOMENTUM]
