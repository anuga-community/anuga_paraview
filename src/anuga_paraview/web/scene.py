"""The VTK scene the web viewer renders: an .sww file's bed and water.

It needs only VTK (the vtk wheel or ParaView's) and the reader's file code,
not trame, so it can be used, and tested, on its own.
"""

import numpy as np

# Load the VTK object factories that render the scene.
import vtkmodules.vtkInteractionStyle  # noqa: F401
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
from vtkmodules.vtkFiltersSources import vtkLineSource
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.vtkRenderingCore import (
    vtkActor, vtkCellPicker, vtkColorTransferFunction, vtkPolyDataMapper,
    vtkRenderWindow, vtkRenderWindowInteractor, vtkRenderer)
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera

from anuga_paraview.plugin.sww_reader import DRY_DEPTH, SWWFile, _surface

# Timesteps sampled to find each quantity's colour range.
RANGE_SAMPLES = 50

# Percentiles of the sampled values that set the colour range, so a few
# extreme values do not leave the rest of the water one colour.
RANGE_PERCENTILES = (1, 99)

# Water shallower than this (m) is hidden to begin with, as in the ParaView
# view, so a film of rain on the ground does not cover the terrain.
WET_DEPTH = 0.05

# Colour maps as (fraction, r, g, b).  The bed is in earth tones; the water
# maps are sampled from matplotlib's, apart from Blues, the ParaView view's.
EARTH = [(0.0, 0.28, 0.42, 0.27), (0.5, 0.71, 0.66, 0.46), (1.0, 0.95, 0.93, 0.88)]
COLOUR_MAPS = {
    'Turbo': [(0.0, 0.19, 0.07, 0.23), (0.125, 0.28, 0.42, 0.89), (0.25, 0.16, 0.74, 0.92),
              (0.375, 0.2, 0.95, 0.59), (0.5, 0.64, 0.99, 0.23), (0.625, 0.93, 0.81, 0.23),
              (0.75, 0.98, 0.49, 0.13), (0.875, 0.82, 0.18, 0.02), (1.0, 0.48, 0.02, 0.01)],
    'Viridis': [(0.0, 0.27, 0.0, 0.33), (0.125, 0.28, 0.18, 0.48), (0.25, 0.23, 0.32, 0.55),
                (0.375, 0.17, 0.45, 0.56), (0.5, 0.13, 0.57, 0.55), (0.625, 0.16, 0.68, 0.5),
                (0.75, 0.37, 0.79, 0.38), (0.875, 0.68, 0.86, 0.19), (1.0, 0.99, 0.91, 0.14)],
    'Plasma': [(0.0, 0.05, 0.03, 0.53), (0.125, 0.3, 0.01, 0.63), (0.25, 0.49, 0.01, 0.66),
               (0.375, 0.67, 0.14, 0.59), (0.5, 0.8, 0.28, 0.47), (0.625, 0.9, 0.43, 0.36),
               (0.75, 0.97, 0.59, 0.25), (0.875, 0.99, 0.77, 0.15), (1.0, 0.94, 0.98, 0.13)],
    'Blues': [(0.0, 0.62, 0.84, 1.0), (1.0, 0.02, 0.11, 0.40)],
}
DEFAULT_MAP = {'depth': 'Turbo', 'speed': 'Plasma', 'stage': 'Viridis', 'momentum': 'Plasma'}

UNITS = {'depth': 'm', 'stage': 'm', 'speed': 'm/s', 'momentum': 'm²/s'}


def _colours(stops, low, high):
    ctf = vtkColorTransferFunction()
    if len(stops) == 2:
        ctf.SetColorSpaceToLab()
    for fraction, r, g, b in stops:
        ctf.AddRGBPoint(low + fraction * (high - low), r, g, b)
    return ctf


class SWWScene(object):
    """The bed and water surfaces of an .sww file at one timestep."""

    def __init__(self, filename):
        self.sww = SWWFile(filename)
        self.quantities = [q for q in ('depth', 'speed', 'stage', 'momentum')
                           if q in self.sww.point_names()]
        self.quantity = 'depth'
        self.wet_depth = WET_DEPTH
        self._ranges = {}

        self.renderer = vtkRenderer()
        self.renderer.SetBackground(0.32, 0.34, 0.43)
        self.renderer.SetBackground2(0.0, 0.0, 0.16)
        self.renderer.GradientBackgroundOn()
        self.window = vtkRenderWindow()
        self.window.AddRenderer(self.renderer)
        self.window.OffScreenRenderingOn()
        interactor = vtkRenderWindowInteractor()
        interactor.SetRenderWindow(self.window)
        interactor.SetInteractorStyle(vtkInteractorStyleTrackballCamera())

        self.bed, self.water = vtkActor(), vtkActor()
        for actor in (self.bed, self.water):
            actor.SetMapper(vtkPolyDataMapper())
            actor.GetMapper().SetScalarModeToUsePointData()
            self.renderer.AddActor(actor)
        self.scalar_bar = vtkScalarBarActor()
        self.scalar_bar.SetNumberOfLabels(5)
        self.scalar_bar.SetMaximumWidthInPixels(80)
        self.renderer.AddViewProp(self.scalar_bar)

        self.picker = vtkCellPicker()
        self.picker.SetTolerance(0.002)

        # A vertical red line marks the picked location.
        self.marker_line = vtkLineSource()
        self.marker = vtkActor()
        self.marker.SetMapper(vtkPolyDataMapper())
        self.marker.GetMapper().SetInputConnection(self.marker_line.GetOutputPort())
        self.marker.GetProperty().SetColor(0.9, 0.1, 0.1)
        self.marker.GetProperty().SetLineWidth(3)
        self.marker.PickableOff()
        self.marker.VisibilityOff()
        self.renderer.AddActor(self.marker)

        self.show(0)
        z = self.sww.point_data(0, ())['elevation']
        self.bed.GetMapper().SetLookupTable(
            _colours(EARTH, float(z.min()), float(z.max())))
        self.bed.GetMapper().SetScalarRange(float(z.min()), float(z.max()))
        self.colour_by(self.quantity)
        self.reset_camera()

    def colour_range(self, quantity):
        """The range of a quantity in the water over (a sample of) the run,
        so colours mean the same at every timestep."""
        if quantity not in self._ranges:
            n = len(self.sww.time)
            samples = []
            for index in sorted(set(range(0, n, max(1, n // RANGE_SAMPLES))) | {n - 1}):
                data = self.sww.point_data(index, (quantity,))
                values = data[quantity][data['depth'] > DRY_DEPTH]
                # A few hundred thousand values a timestep are plenty.
                samples.append(values[::max(1, len(values) // 200000)])
            values = np.concatenate(samples)
            if len(values):
                low, high = (float(v) for v in np.percentile(values, RANGE_PERCENTILES))
            else:
                low, high = 0.0, 0.0
            if quantity != 'stage':
                low = 0.0
            if high <= low:
                high = low + 0.01
            self._ranges[quantity] = (low, high)
        return self._ranges[quantity]

    def colour_by(self, quantity, colour_map=None, high=None):
        """Colour the water by a quantity, up to high if given, else the
        top of its usual range."""
        self.quantity = quantity
        low, auto_high = self.colour_range(quantity)
        high = auto_high if high is None or high <= low else high
        lut = _colours(COLOUR_MAPS[colour_map or DEFAULT_MAP[quantity]], low, high)
        mapper = self.water.GetMapper()
        mapper.SetLookupTable(lut)
        mapper.SetScalarRange(low, high)
        mapper.SelectColorArray(quantity)
        mapper.SetScalarModeToUsePointFieldData()
        self.scalar_bar.SetLookupTable(lut)
        self.scalar_bar.SetTitle('%s (%s)' % (quantity.capitalize(), UNITS[quantity]))

    def show(self, index):
        """Build the surfaces for a timestep."""
        self.index = index
        sww = self.sww
        data = sww.point_data(index, self.quantities)
        bed = _surface(sww.x, sww.y, data['elevation'], sww.triangles,
                       {'elevation': data['elevation']}, {}, 'elevation')
        wet_depth = max(DRY_DEPTH, self.wet_depth)
        wet = (data['depth'][sww.triangles] > wet_depth).any(axis=1)
        water = _surface(sww.x, sww.y, data['stage'], sww.triangles,
                         data, {}, 'depth', keep=wet)
        self.bed.GetMapper().SetInputData(bed)
        self.water.GetMapper().SetInputData(water)

    def set_vertical_scale(self, scale):
        for actor in (self.bed, self.water, self.marker):
            actor.SetScale(1.0, 1.0, scale)

    def reset_camera(self):
        """An oblique view from the south, like anuga_viewer's."""
        xmin, xmax, ymin, ymax, zmin, zmax = self.bed.GetBounds()
        centre = [(xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2]
        size = max(xmax - xmin, ymax - ymin)
        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(centre)
        camera.SetPosition(centre[0], centre[1] - 1.2 * size, centre[2] + 0.9 * size)
        camera.SetViewUp(0, 0, 1)
        self.renderer.ResetCamera()

    def pick(self, x, y):
        """The (x, y) in file coordinates under a pixel, or None."""
        if not self.picker.Pick(x, y, 0, self.renderer):
            return None
        px, py, _ = self.picker.GetPickPosition()
        zmin, zmax = self.bed.GetMapper().GetInput().GetBounds()[4:]
        height = zmax - zmin
        self.marker_line.SetPoint1(px, py, zmin)
        self.marker_line.SetPoint2(px, py, zmax + 0.5 * height)
        self.marker.VisibilityOn()
        return px, py
