# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

`anuga_paraview` views ANUGA `.sww` files (NetCDF: a triangular mesh, bed elevation, and stage/momentum per timestep) in ParaView and in a web browser. It reads the files with `netCDF4` (or `scipy`) and does not depend on ANUGA. It came out of anuga-viewer's `paraview/` directory, with its history.

## Layout

- `src/anuga_paraview/plugin/sww_reader.py`: the ParaView plugin, `ANUGASWWReader` (outputs `Bed`, z = elevation, and `Water`, z = stage with dry triangles dropped, with every point/cell variable plus derived depth, speed, momentum and velocity) and the `ANUGATimeseries` filter. `SWWFile` is the file code, read one timestep (or one triangle's corners) at a time. **The plugin must stay alone in `plugin/`**: ParaView loads every `.py` in a `PV_PLUGIN_PATH` directory, so there is no `__init__.py` there (it is a namespace package). It must keep working with only numpy and netCDF4/scipy, since ParaView's bundled Python may not have `anuga_paraview` installed; outside ParaView its GUI decorators are no-ops and it runs as a plain VTK algorithm.
- `src/anuga_paraview/scripts/view_sww.py`: a ParaView script that sets up a ready-made view. It finds the plugin by path, not by import.
- `src/anuga_paraview/cli.py`: `anuga-paraview [file.sww] [--plugin-path] [--paraview PATH]`, which runs ParaView with `PV_PLUGIN_PATH` set and the view script.
- `src/anuga_paraview/web/scene.py`: `SWWScene`, the VTK scene of the web viewer (needs only VTK). `web/app.py`: the trame app, `anuga-web-viewer file.sww --port 8080`. `build(server, filename)` sets up a server; `main()` runs it.
- `data/`: sample `.sww` files used by the tests.

## Testing

```bash
pip install -e ".[web,test]"
python -m pytest
ruff check .
```

`tests/paraview/` runs the reader inside ParaView and is skipped unless `paraview.simple` imports (e.g. a conda env with `conda-forge::paraview netcdf4 pytest`, and `pip install -e . --no-deps`). Everything else needs only the pip `vtk` wheel, which renders headless through EGL/OSMesa. CI (`.github/workflows/ci.yml`) runs both, on Linux, macOS and Windows for pip vtk.

On a Wayland desktop ParaView may hang at startup: the launcher sets `QT_QPA_PLATFORM=xcb`.
