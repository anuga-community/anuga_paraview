"""The VTK scene the web viewer renders: an .sww file's bed and water.

It needs only VTK (the vtk wheel or ParaView's) and the reader's file code,
not trame, so it can be used, and tested, on its own.
"""

import ctypes.util
import os
import sys

import numpy as np

# Load the VTK object factories that render the scene.
import vtkmodules.vtkInteractionStyle  # noqa: F401
import vtkmodules.vtkRenderingFreeType  # noqa: F401
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
from vtkmodules.vtkFiltersSources import vtkLineSource
from vtkmodules.vtkIOImage import vtkPNGWriter
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.vtkRenderingCore import (
    vtkActor, vtkCellPicker, vtkColorTransferFunction, vtkPolyDataMapper,
    vtkRenderWindow, vtkRenderWindowInteractor, vtkRenderer, vtkTextActor,
    vtkWindowToImageFilter)
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera

from anuga_paraview.plugin.sww_reader import DRY_DEPTH, SWWFile, _surface
from anuga_paraview.web.clock import Clock
from anuga_paraview.web.georef import Georeference

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


def headless_window(environ=None, find_library=ctypes.util.find_library):
    """The VTK render window class to ask for on a Linux machine without a
    display, or None to leave the choice to VTK.

    Left to itself, VTK tries X first and logs "bad X server connection"
    before falling back to offscreen rendering.  Only X counts as a display:
    VTK draws in a window through X, or through XWayland on Wayland."""
    environ = os.environ if environ is None else environ
    if (not sys.platform.startswith('linux') or 'VTK_DEFAULT_OPENGL_WINDOW' in environ
            or environ.get('DISPLAY')):
        return None
    if find_library('EGL'):
        return 'vtkEGLRenderWindow'
    if find_library('OSMesa'):
        return 'vtkOSMesaRenderWindow'
    return None


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
        self.clock = Clock(self.sww.time, self.sww.attrs)
        self.georef = Georeference(self.sww.attrs)
        self.quantities = [q for q in ('depth', 'speed', 'stage', 'momentum')
                           if q in self.sww.point_names()]
        self.quantity = 'depth'
        self.wet_depth = WET_DEPTH
        self.view_2d = False
        self._ranges = {}
        self._maxima = None

        window_class = headless_window()
        if window_class:
            os.environ['VTK_DEFAULT_OPENGL_WINDOW'] = window_class

        self.renderer = vtkRenderer()
        self.renderer.SetBackground(0.32, 0.34, 0.43)
        self.renderer.SetBackground2(0.0, 0.0, 0.16)
        self.renderer.GradientBackgroundOn()
        self.window = vtkRenderWindow()
        self.window.AddRenderer(self.renderer)
        self.window.OffScreenRenderingOn()
        interactor = vtkRenderWindowInteractor()
        interactor.SetRenderWindow(self.window)
        self.style = vtkInteractorStyleTrackballCamera()
        interactor.SetInteractorStyle(self.style)

        self.bed, self.water = vtkActor(), vtkActor()
        for actor in (self.bed, self.water):
            actor.SetMapper(vtkPolyDataMapper())
            actor.GetMapper().SetScalarModeToUsePointData()
            self.renderer.AddActor(actor)
        self.scalar_bar = vtkScalarBarActor()
        self.scalar_bar.SetNumberOfLabels(5)
        self.scalar_bar.SetMaximumWidthInPixels(80)
        self.renderer.AddViewProp(self.scalar_bar)

        # The time in the corner, so it is in saved pictures too.
        self.caption = vtkTextActor()
        self.caption.GetTextProperty().SetFontSize(18)
        self.caption.GetTextProperty().SetColor(1, 1, 1)
        self.caption.SetPosition(10, 10)
        self.renderer.AddViewProp(self.caption)

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

    @property
    def maximum_index(self):
        """The index past the last timestep that shows the maxima over the run."""
        return len(self.sww.time)

    def maxima(self):
        """The bed at the end of the run, with the maximum stage, depth, speed
        and momentum over it; read once, on first use."""
        if self._maxima is None:
            last = self.sww.point_data(len(self.sww.time) - 1, ())
            data = {'elevation': last['elevation']}
            for name, values in self.sww.maxima().items():
                data[name[len('max_'):]] = values
            self._maxima = data
        return self._maxima

    def time_label(self, index):
        if index == self.maximum_index:
            return 'Maximum over the run'
        return self.clock.label(index)

    def show(self, index):
        """Build the surfaces for a timestep, or for the maxima over the run
        at maximum_index."""
        self.index = index
        sww = self.sww
        if index == self.maximum_index:
            data = self.maxima()
        else:
            data = sww.point_data(index, self.quantities)
        self.caption.SetInput(self.time_label(index))
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
        """An oblique view from the south, like anuga_viewer's, or in 2D a
        map view from above with north up."""
        xmin, xmax, ymin, ymax, zmin, zmax = self.bed.GetBounds()
        centre = [(xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2]
        size = max(xmax - xmin, ymax - ymin)
        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(centre)
        if self.view_2d:
            camera.SetPosition(centre[0], centre[1], centre[2] + 2 * size)
            camera.SetViewUp(0, 1, 0)
        else:
            camera.SetPosition(centre[0], centre[1] - 1.2 * size, centre[2] + 0.9 * size)
            camera.SetViewUp(0, 0, 1)
        self.renderer.ResetCamera()

    def set_view_2d(self, view_2d):
        """Switch between the 3D view and a 2D map view from above, in which
        dragging with the left button pans rather than rotates."""
        self.view_2d = bool(view_2d)
        self.renderer.GetActiveCamera().SetParallelProjection(self.view_2d)
        style = self.style
        # An observer on the style replaces its own handling of the event.
        style.RemoveObservers('LeftButtonPressEvent')
        style.RemoveObservers('LeftButtonReleaseEvent')
        if self.view_2d:
            style.AddObserver('LeftButtonPressEvent', lambda obj, event: obj.OnMiddleButtonDown())
            style.AddObserver('LeftButtonReleaseEvent', lambda obj, event: obj.OnMiddleButtonUp())
        self.reset_camera()

    def png(self):
        """The current view as PNG bytes."""
        self.window.Render()
        grab = vtkWindowToImageFilter()
        grab.SetInput(self.window)
        grab.ReadFrontBufferOff()
        grab.Update()
        writer = vtkPNGWriter()
        writer.WriteToMemoryOn()
        writer.SetInputConnection(grab.GetOutputPort())
        writer.Write()
        return bytes(memoryview(writer.GetResult()))

    def pick(self, x, y):
        """The (x, y) in the file's local coordinates under a pixel, or None."""
        if not self.picker.Pick(x, y, 0, self.renderer):
            return None
        px, py, _ = self.picker.GetPickPosition()
        zmin, zmax = self.bed.GetMapper().GetInput().GetBounds()[4:]
        height = zmax - zmin
        self.marker_line.SetPoint1(px, py, zmin)
        self.marker_line.SetPoint2(px, py, zmax + 0.5 * height)
        self.marker.VisibilityOn()
        return px, py
