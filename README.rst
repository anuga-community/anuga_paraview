anuga_paraview
==============

View ANUGA_ ``.sww`` files in ParaView_, and in a web browser.

- A **ParaView reader** that opens ``.sww`` files, with an **ANUGA
  Timeseries** filter that plots quantities at a point straight from the
  file.
- ``anuga-paraview``, which starts ParaView with the reader loaded and a
  ready-made view of a file.
- ``anuga-web-viewer``, a browser viewer built with trame_ on plain VTK.
  The server reads the file and renders, so a large file on a remote
  machine can be viewed without copying it.  It does not need ParaView.

Neither needs ANUGA itself: they read the files with ``netCDF4``.  The
other viewers are anuga-viewer_, a fast native 3D viewer, and ANUGA's
``anuga_sww_gui``, for exporting frames and plotting timeseries and
cross-section flows.

This is early work; the reader and the web viewer are prototypes.

.. _ANUGA: https://github.com/anuga-community/anuga_core
.. _ParaView: https://www.paraview.org
.. _anuga-viewer: https://github.com/anuga-community/anuga-viewer

Installing
----------

For ParaView, the conda-forge build is the easiest, since the reader needs
``netCDF4`` (or ``scipy``) in ParaView's Python::

    conda create -n paraview -c conda-forge paraview netcdf4
    conda activate paraview
    pip install anuga-paraview

It is tested with ParaView 6.2; older 5.x releases may work but are
untested.

For the web viewer alone, no ParaView or conda is needed::

    pip install "anuga-paraview[web]"

The development version installs with
``pip install git+https://github.com/anuga-community/anuga_paraview``.

Quick start
-----------

``anuga-paraview`` starts ParaView with the reader loaded, and given a
file, opens it with a ready-made view::

    anuga-paraview            # open .sww files with File > Open
    anuga-paraview run.sww

The bed is coloured by elevation and the water by depth, with water under
5 cm faded out so the terrain shows through, and the depth colour range
fixed over the run.  A time label sits in the corner; press Play on the
animation toolbar.  The setup is in ``scripts/view_sww.py``: to apply it
to a ``.sww`` opened with File > Open, select the file in the Pipeline
Browser and run the script from View > Python Shell > Run Script, or add
it once as a toolbar button with Macros > Import new macro.

The launcher uses the ``paraview`` on the PATH, or the one given by
``--paraview`` or ``$PARAVIEW``, and runs it on X11 when the session is
Wayland.

``anuga-web-viewer run.sww`` serves the browser viewer; see `Web viewer`_.

Loading
-------

In the ParaView GUI, use Tools > Manage Plugins > Load New... and pick
``sww_reader.py``, in the directory ``anuga-paraview --plugin-path``
prints.  Tick *Auto Load* to have it every session.  ``.sww``
files then open with File > Open like any other format.

From ``pvpython``::

    from paraview.simple import *
    LoadPlugin('/path/to/anuga_paraview/plugin/sww_reader.py', ns=globals())
    sww = OpenDataFile('run.sww')

To read files on a remote machine with ``pvserver``, load the plugin on both
the client and the server (the Manage Plugins dialog has a list for each),
and install ``netCDF4`` in the server's Python.

Outputs
-------

The reader has two outputs, matching ``anuga_viewer``:

``Bed``
    The terrain, with z = elevation.
``Water``
    The water surface, with z = stage.  Triangles whose three vertices are
    all shallower than 1 mm are left out, unless *ShowDryWater* is on.

Both carry the same arrays at each timestep:

- every per-point variable in the file (``stage``, ``elevation``,
  ``xmomentum``, ``friction``, ...) as point data;
- every per-triangle variable (``stage_c``, ``max_depth_c``, ...) as cell
  data;
- derived ``depth``, and where momentum is present ``momentum``, ``speed``
  and a ``velocity`` vector, with speed zero where depth is below 1 mm.
  The same are derived per triangle (``depth_c``, ``speed_c``, ...) when the
  file has ``stage_c`` and ``elevation_c``.

Properties
----------

``Point Arrays`` / ``Cell Arrays``
    Shown with the gear (advanced) button at the top of the Properties
    panel.  The arrays the file offers, per point and per triangle, all
    ticked to begin with.  Unticked arrays are not read, except where a
    ticked derived quantity needs them (``speed`` reads both momentum
    components).  Elevation and stage are always read, since the surfaces
    are built from them.
``VerticalScale``
    Vertical exaggeration of both surfaces, like ``anuga_viewer -scale``.
``Georeferenced``
    Add the file's ``xllcorner``/``yllcorner``, giving projected (e.g. UTM)
    coordinates rather than the local ones stored in the file.
``ShowDryWater``
    Keep dry triangles in the ``Water`` output.
``ComputeMaxima``
    Add ``max_stage``, ``max_depth``, ``max_speed`` and ``max_momentum`` over
    all timesteps.  This reads the whole file once.

``Bed`` is coloured by ``elevation`` and ``Water`` by ``depth`` to begin
with; ``speed`` is often more telling.  ParaView fixes the colour range when
you press Apply, which is usually the dry first timestep, so press *Rescale
to data range over all timesteps* on the colour toolbar before playing the
animation.

On Linux under Wayland, if ParaView hangs at startup, run it on X11::

    QT_QPA_PLATFORM=xcb paraview

If it still hangs, add ``LIBGL_ALWAYS_SOFTWARE=1`` to use software OpenGL.

Setting ``PV_PLUGIN_PATH`` to the plugin directory loads the reader without
the Manage Plugins dialog::

    PV_PLUGIN_PATH=$(anuga-paraview --plugin-path) paraview run.sww

The plugin is alone in that directory because ParaView loads every ``.py``
file on ``PV_PLUGIN_PATH`` as a plugin.  It needs only ``numpy`` and
``netCDF4`` (or ``scipy``), so a ParaView with its own Python, such as the
binaries from paraview.org, can load it by path without ``anuga_paraview``
being installed there.

Timeseries at a point
---------------------

The plugin also adds an **ANUGA Timeseries** filter.  It reads the values
at one location straight from the file, so it is instant even for long
runs, where ParaView's Plot Selection Over Time re-reads every timestep in
full.

1. Select ``Bed`` (or ``Water``) in the Pipeline Browser.
2. Add the filter: Filters > ANUGA > ANUGA Timeseries, or Ctrl+Space and
   type "ANUGA".
3. Click Apply.  A line chart of depth and speed against time opens beside
   the 3D view, for the middle of the domain.
4. Move the location: click in the 3D view, hover over the spot and press
   **P**, or drag the marker, or type coordinates into *Location*.  Then
   click Apply.  For the chart to follow the marker without Apply, tick
   *Auto Apply* in Edit > Settings > General (under Properties Panel
   Options).
5. Tick other quantities under *Quantities*: stage, elevation, momentum
   and its components.

Values are interpolated from the corners of the triangle containing the
location, as ANUGA's own gauge tools do.  Only x and y matter.  File >
Save Data writes the chart's table as CSV.

Web viewer
----------

``anuga-web-viewer`` is a browser viewer built with trame_.  It reuses the
reader's file code with plain VTK, so it does not need ParaView::

    pip install "anuga-paraview[web]"
    anuga-web-viewer run.sww --port 8080

and open http://localhost:8080.  The server reads the file and renders, and
the browser only receives images, so a large file on a remote machine can
be viewed through ``ssh -L 8080:localhost:8080 host``.

- The bed and water with a time slider and Play.  Times are shown as hours
  since the start, or, when the file's ``starttime`` is a date, as the date
  and time in its ``timezone``.  The last position of the slider shows the
  maximum depth, speed, stage or momentum over the run.
- The side panel sets the quantity the water is coloured by, the colour
  map and scale maximum, the depth below which water is hidden, and the
  vertical scale.
- *Pick a point* plots a timeseries there and gives its projected
  coordinates and, for UTM-based systems (WGS 84, GDA2020, GDA94, AGD,
  ETRS89), its EPSG code and latitude and longitude.
- The toolbar switches between the 3D view and a 2D map view from above,
  resets the view, and saves it as a PNG.

It works with the ``vtk`` wheel from pip, which renders without a display
(through EGL or OSMesa) on a headless server, and with the VTK in
ParaView's conda package.  It serves one user at a time.

.. _trame: https://kitware.github.io/trame/

Testing
-------

::

    pip install -e ".[web,test]"
    python -m pytest

checks the reader's file code, the reader as a plain VTK algorithm, the web
viewer and the launcher against the sample files in ``data/``, comparing
with values read directly from the files.  In an environment with
ParaView (``conda install -c conda-forge paraview``), the same command also
checks the reader inside ParaView (``tests/paraview/``); elsewhere those
tests are skipped.

Releasing
---------

Set ``__version__`` in ``src/anuga_paraview/__init__.py``, merge, then
publish a GitHub release tagged ``v`` plus that version (e.g. ``v0.1.0``).
The Release workflow builds the sdist and wheel, checks the tag matches the
version, and uploads them to PyPI by trusted publishing.

License
-------

Apache License 2.0, as for ANUGA.
