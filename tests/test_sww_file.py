"""The reader's file code, and the reader run as a plain VTK algorithm.

These need VTK but not ParaView: outside ParaView the reader's GUI
decorators are no-ops.  tests/paraview/ checks the reader inside ParaView.
"""

import netCDF4
import numpy as np
import pytest

pytest.importorskip('vtkmodules')
from vtkmodules.util.numpy_support import vtk_to_numpy  # noqa: E402

from anuga_paraview.plugin import sww_reader  # noqa: E402

from conftest import DAM_BREAK, NO_MOMENTUM  # noqa: E402


def _reference(path):
    """Mesh and variables read directly from the file."""
    nc = netCDF4.Dataset(path)
    nc.set_auto_mask(False)
    bed = 'elevation' if 'elevation' in nc.variables else 'z'
    ref = dict(x=nc['x'][:], y=nc['y'][:], triangles=nc['volumes'][:],
               time=np.atleast_1d(nc['time'][:]), stage=nc['stage'][:],
               elev=nc[bed][:], xllcorner=float(getattr(nc, 'xllcorner', 0.0)))
    if 'xmomentum' in nc.variables:
        ref['xmom'], ref['ymom'] = nc['xmomentum'][:], nc['ymomentum'][:]
    nc.close()
    return ref


def _elev(ref, index):
    return ref['elev'][index] if ref['elev'].ndim == 2 else ref['elev']


def test_mesh_and_times_match_the_file(sww_path):
    ref = _reference(sww_path)
    sww = sww_reader.SWWFile(sww_path)
    assert np.allclose(sww.x, ref['x']) and np.allclose(sww.y, ref['y'])
    assert np.array_equal(sww.triangles, ref['triangles'])
    assert np.allclose(sww.time, ref['time'])
    sww.close()


def test_point_data_matches_the_file(sww_path):
    ref = _reference(sww_path)
    sww = sww_reader.SWWFile(sww_path)
    index = len(ref['time']) * 2 // 3
    data = sww.point_data(index)
    stage, elev = ref['stage'][index], _elev(ref, index)
    assert np.allclose(data['stage'], stage)
    assert np.allclose(data['elevation'], elev)
    assert np.allclose(data['depth'], np.maximum(stage - elev, 0), atol=1e-5)
    if 'xmom' in ref:
        depth = data['depth']
        wet = depth > sww_reader.DRY_DEPTH
        speed = np.hypot(ref['xmom'][index], ref['ymom'][index])
        assert np.allclose(data['speed'][wet], speed[wet] / depth[wet], rtol=1e-4)
        assert np.all(data['speed'][~wet] == 0)
    else:
        assert 'speed' not in sww.point_names()
    sww.close()


def test_only_the_variables_needed_are_read():
    sww = sww_reader.SWWFile(DAM_BREAK)
    read = []
    original = sww._read
    sww._read = lambda name, animated, i: read.append(name) or original(name, animated, i)
    sww.point_data(3, ['stage'])
    assert set(read) == {'elevation', 'stage'}
    del read[:]
    sww.point_data(3, ['speed'])
    assert set(read) == {'elevation', 'stage', 'xmomentum', 'ymomentum'}
    del read[:]
    sww.cell_data(3, [])
    assert read == []
    sww.close()


@pytest.mark.parametrize('path', [NO_MOMENTUM, DAM_BREAK], ids=['cairns', 'dam-break'])
def test_timeseries_at_a_centroid_is_the_mean_of_its_corners(path):
    ref = _reference(path)
    sww = sww_reader.SWWFile(path)
    k = len(ref['triangles']) // 2
    corners = ref['triangles'][k]
    px = ref['x'][corners].astype(np.float64).mean()
    py = ref['y'][corners].astype(np.float64).mean()
    series = sww.timeseries(px, py, ['stage', 'depth'])
    stage = ref['stage'][:, corners].mean(axis=1)
    elev = ref['elev'][:, corners].mean(axis=1) if ref['elev'].ndim == 2 \
        else ref['elev'][corners].mean()
    assert np.allclose(series['stage'], stage, atol=1e-5)
    assert np.allclose(series['depth'], np.maximum(stage - elev, 0), atol=1e-5)
    assert sww.timeseries(-1e9, -1e9, ['stage']) is None
    sww.close()


def test_maxima_bound_every_timestep():
    sww = sww_reader.SWWFile(DAM_BREAK)
    maxima = sww.maxima()
    for index in range(len(sww.time)):
        data = sww.point_data(index, ('speed',))
        assert np.all(maxima['max_depth'] >= data['depth'])
        assert np.all(maxima['max_speed'] >= data['speed'])
    sww.close()


def _run(reader, time, port):
    reader.UpdateTimeStep(time)
    return reader.GetOutputDataObject(port)


def test_the_reader_runs_as_a_vtk_algorithm(sww_path):
    ref = _reference(sww_path)
    reader = sww_reader.ANUGASWWReader()
    reader.SetFileName(sww_path)
    reader.UpdateInformation()
    assert np.allclose(reader.GetTimestepValues(), ref['time'])

    index = len(ref['time']) * 2 // 3
    t = float(ref['time'][index])
    bed = _run(reader, t, 0)
    water = _run(reader, t, 1)
    elev, stage = _elev(ref, index), ref['stage'][index]
    assert bed.GetNumberOfCells() == len(ref['triangles'])
    assert np.allclose(vtk_to_numpy(bed.GetPoints().GetData())[:, 2], elev)
    assert np.allclose(vtk_to_numpy(water.GetPoints().GetData())[:, 2], stage)

    depth = np.maximum(stage - elev, 0)
    wet = (depth[ref['triangles']] > sww_reader.DRY_DEPTH).any(axis=1)
    assert water.GetNumberOfCells() == int(wet.sum())

    reader.SetVerticalScale(2.0)
    assert np.allclose(vtk_to_numpy(_run(reader, t, 0).GetPoints().GetData())[:, 2], 2 * elev)
    reader.SetVerticalScale(1.0)
    reader.SetGeoreferenced(1)
    xs = vtk_to_numpy(_run(reader, t, 0).GetPoints().GetData())[:, 0]
    assert np.allclose(xs, ref['x'].astype(np.float64) + ref['xllcorner'])
