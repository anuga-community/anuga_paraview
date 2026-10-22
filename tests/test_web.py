"""The web viewer's scene (VTK only) and its trame app."""

import numpy as np
import pytest

pytest.importorskip('vtkmodules')
from anuga_paraview.web.scene import COLOUR_MAPS, DEFAULT_MAP, SWWScene  # noqa: E402

from conftest import DAM_BREAK, NO_MOMENTUM  # noqa: E402


def test_quantities_follow_the_file():
    assert SWWScene(NO_MOMENTUM).quantities == ['depth', 'stage']
    assert SWWScene(DAM_BREAK).quantities == ['depth', 'speed', 'stage', 'momentum']


def test_colour_ranges_cover_the_water():
    scene = SWWScene(DAM_BREAK)
    low, high = scene.colour_range('depth')
    assert low == 0.0 and high > 0.0
    low, high = scene.colour_range('stage')
    assert low < high
    depth_max = max(scene.sww.point_data(i, ())['depth'].max() for i in range(len(scene.sww.time)))
    assert scene.colour_range('depth')[1] <= depth_max


def test_colour_by_sets_the_map_and_range():
    scene = SWWScene(DAM_BREAK)
    scene.colour_by('speed', 'Viridis', 2.5)
    mapper = scene.water.GetMapper()
    assert mapper.GetArrayName() == 'speed'
    assert mapper.GetScalarRange() == (0.0, 2.5)
    first = COLOUR_MAPS['Viridis'][0][1:]
    assert np.allclose(mapper.GetLookupTable().GetColor(0.0), first)
    scene.colour_by('speed')               # back to the default map and range
    default = COLOUR_MAPS[DEFAULT_MAP['speed']][0][1:]
    assert np.allclose(mapper.GetLookupTable().GetColor(0.0), default)
    assert mapper.GetScalarRange()[1] == pytest.approx(scene.colour_range('speed')[1])


def test_shallow_water_is_hidden():
    scene = SWWScene(DAM_BREAK)
    last = len(scene.sww.time) - 1
    counts = []
    for wet_depth in (0.0, 0.05, 0.5):
        scene.wet_depth = wet_depth
        scene.show(last)
        counts.append(scene.water.GetMapper().GetInput().GetNumberOfCells())
    assert counts[0] >= counts[1] >= counts[2]
    assert counts[0] > counts[2]


def test_vertical_scale_stretches_every_actor():
    scene = SWWScene(DAM_BREAK)
    scene.set_vertical_scale(3.0)
    for actor in (scene.bed, scene.water, scene.marker):
        assert actor.GetScale() == (1.0, 1.0, 3.0)


def test_the_app_builds_and_reacts_to_its_state():
    pytest.importorskip('trame')
    from trame.app import get_server
    from anuga_paraview.web import app

    server = get_server('test_app', client_type='vue3')
    scene = app.build(server, DAM_BREAK)
    state = server.state
    assert state.quantities == scene.quantities
    assert state.colour_map == DEFAULT_MAP['depth']
    state.ready()                          # as server.start() does

    state.quantity = 'speed'
    state.flush()
    assert scene.quantity == 'speed'
    assert state.colour_map == DEFAULT_MAP['speed']

    state.index = 5
    state.flush()
    assert scene.index == 5
    assert state.time_label == 'Time: %.1f s' % scene.sww.time[5]


RENDER = """
import sys
import numpy as np
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
from anuga_paraview.web.scene import SWWScene
scene = SWWScene(sys.argv[1])
scene.window.SetSize(400, 300)
scene.show(15)
scene.window.Render()
grab = vtkWindowToImageFilter()
grab.SetInput(scene.window)
grab.Update()
pixels = vtk_to_numpy(grab.GetOutput().GetPointData().GetScalars())
print(len(np.unique(pixels, axis=0)))
print(scene.pick(200, 150) is not None, scene.pick(2, 2) is None)
"""


def test_the_scene_renders_and_picks_offscreen():
    # In a subprocess: without a usable OpenGL, VTK aborts rather than raising.
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-c', RENDER, DAM_BREAK],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    colours, picks = result.stdout.split('\n')[:2]
    assert int(colours) > 100                  # a picture, not a blank window
    assert picks == 'True True'                # the middle hits, a corner misses
