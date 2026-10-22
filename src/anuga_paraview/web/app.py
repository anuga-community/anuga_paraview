"""View an ANUGA .sww file in a web browser.

A minimal trame app: the server reads the file and renders, and the browser
shows the picture, so only the image travels, not the mesh.  Install it with

    pip install anuga-paraview[web]

Run it where the file is, then open the URL it prints:

    anuga-web-viewer run.sww --port 8080

On a remote machine, start it with --host 0.0.0.0, or tunnel the port with
ssh -L 8080:localhost:8080 hpc and open http://localhost:8080.
"""

import asyncio
import os
import sys

from trame.app import get_server
from trame.ui.vuetify3 import SinglePageWithDrawerLayout
from trame.widgets import plotly, vuetify3 as v3, vtk as vtk_widgets

import plotly.graph_objects as go

from anuga_paraview.web.scene import COLOUR_MAPS, DEFAULT_MAP, UNITS, WET_DEPTH, SWWScene

# Seconds between frames when playing.
FRAME_DELAY = 0.1


def build(server, filename):
    """Set up the viewer for a file on a trame server; returns the scene."""
    state, ctrl = server.state, server.controller

    scene = SWWScene(filename)
    times = scene.sww.time

    state.trame__title = os.path.basename(filename)
    state.index = 0
    state.time_label = 'Time: %.1f s' % times[0]
    state.playing = False
    state.quantity = scene.quantity
    state.quantities = scene.quantities
    state.colour_map = DEFAULT_MAP[scene.quantity]
    state.colour_maps = list(COLOUR_MAPS)
    state.colour_max = float('%.3g' % scene.colour_range(scene.quantity)[1])
    state.wet_depth = WET_DEPTH
    state.units = UNITS
    state.vertical_scale = 1.0
    state.picking = False
    state.pick_modes = []
    state.location = ''
    state.series = None

    def _chart():
        """A plot of the picked location's depth and the colour quantity."""
        if state.series is None:
            return go.Figure()
        x, y = state.series
        wanted = ['depth'] if scene.quantity == 'depth' else ['depth', scene.quantity]
        data = scene.sww.timeseries(x, y, wanted)
        fig = go.Figure()
        if data is None:
            fig.add_annotation(text='Outside the mesh', showarrow=False)
        else:
            for i, name in enumerate(wanted):
                fig.add_trace(go.Scatter(x=times, y=data[name], name=name,
                                         yaxis='y' if i == 0 else 'y2'))
            fig.add_vline(x=float(times[state.index]), line_color='grey', line_dash='dot')
            fig.update_layout(yaxis=dict(title='%s (%s)' % (wanted[0], UNITS[wanted[0]])))
            if len(wanted) > 1:
                fig.update_layout(yaxis2=dict(title='%s (%s)' % (wanted[1], UNITS[wanted[1]]),
                                              overlaying='y', side='right'))
        fig.update_layout(margin=dict(l=40, r=40, t=10, b=30), height=260,
                          xaxis_title='Time (s)', legend=dict(orientation='h', y=1.12))
        return fig

    @state.change('index')
    def on_index(index, **_):
        scene.show(int(index))
        state.time_label = 'Time: %.1f s' % times[int(index)]
        if state.series is not None:
            ctrl.chart_update(_chart())
        ctrl.view_update()

    @state.change('quantity')
    def on_quantity(quantity, **_):
        state.colour_map = DEFAULT_MAP[quantity]
        state.colour_max = float('%.3g' % scene.colour_range(quantity)[1])
        scene.colour_by(quantity, state.colour_map, state.colour_max)
        if state.series is not None:
            ctrl.chart_update(_chart())
        ctrl.view_update()

    @state.change('colour_map')
    def on_colour_map(colour_map, **_):
        scene.colour_by(scene.quantity, colour_map, _colour_max())
        ctrl.view_update()

    def _colour_max():
        try:
            return float(state.colour_max)
        except (TypeError, ValueError):
            return None

    @state.change('colour_max')
    def on_colour_max(**_):
        scene.colour_by(scene.quantity, state.colour_map, _colour_max())
        ctrl.view_update()

    @state.change('wet_depth')
    def on_wet_depth(wet_depth, **_):
        scene.wet_depth = float(wet_depth)
        scene.show(scene.index)
        ctrl.view_update()

    @state.change('vertical_scale')
    def on_vertical_scale(vertical_scale, **_):
        scene.set_vertical_scale(float(vertical_scale))
        ctrl.view_update()

    @state.change('picking')
    def on_picking(picking, **_):
        state.pick_modes = ['click'] if picking else []

    @state.change('playing')
    def on_playing(playing, **_):
        if playing:
            asyncio.ensure_future(_play())

    async def _play():
        while state.playing:
            with state:
                state.index = (state.index + 1) % len(times)
            await asyncio.sleep(FRAME_DELAY)

    def on_click(event):
        """Pick the location under a click; the browser's canvas may be a
        different size from the server's window, so scale the position."""
        width, height = scene.window.GetSize()
        sx, sy = event['size']
        found = scene.pick(event['position']['x'] * width / sx,
                           event['position']['y'] * height / sy)
        state.picking = False
        if found is None:
            return
        ctrl.view_update()
        state.series = found
        state.location = 'x = %.1f, y = %.1f' % found
        ctrl.chart_update(_chart())

    def reset_camera():
        scene.reset_camera()
        ctrl.view_update()

    with SinglePageWithDrawerLayout(server) as layout:
        layout.title.set_text(os.path.basename(filename))
        with layout.toolbar:
            v3.VSpacer()
            v3.VBtn(icon=("playing ? 'mdi-pause' : 'mdi-play'",),
                    click='playing = !playing', variant='text')
            v3.VSlider(v_model=('index', 0), min=0, max=len(times) - 1, step=1,
                       hide_details=True, density='compact', style='max-width: 400px')
            v3.VLabel('{{ time_label }}', classes='mx-4', style='min-width: 120px')
            v3.VBtn(icon='mdi-crop-free', click=reset_camera, variant='text')

        with layout.drawer as drawer:
            drawer.width = 420
            with v3.VContainer():
                v3.VSelect(label='Colour water by', v_model=('quantity',),
                           items=('quantities',), density='compact')
                v3.VSelect(label='Colour map', v_model=('colour_map',),
                           items=('colour_maps',), density='compact')
                v3.VTextField(label='Colour scale maximum', v_model=('colour_max',),
                              type='number', suffix=('units[quantity]',),
                              density='compact')
                v3.VSlider(label='Hide water shallower than (m)',
                           v_model=('wet_depth', WET_DEPTH), min=0, max=0.5, step=0.01,
                           thumb_label=True, density='compact')
                v3.VSlider(label='Vertical scale', v_model=('vertical_scale', 1.0),
                           min=0.5, max=20, step=0.5, thumb_label=True,
                           density='compact')
                v3.VBtn('Pick a point', prepend_icon='mdi-crosshairs-gps',
                        click='picking = true', block=True,
                        color=("picking ? 'primary' : undefined",))
                v3.VLabel("{{ picking ? 'Click on the surface' : location }}",
                          classes='my-2')
                figure = plotly.Figure(display_mode_bar=False, v_show='series')
                ctrl.chart_update = figure.update

        with layout.content:
            with v3.VContainer(fluid=True, classes='pa-0 fill-height'):
                view = vtk_widgets.VtkRemoteView(
                    scene.window, interactive_ratio=1,
                    picking_modes=('pick_modes',),
                    click=(on_click, '[$event]'))
                ctrl.view_update = view.update

    return scene


def main():
    server = get_server(client_type='vue3')
    server.cli.add_argument('sww', help='the .sww file to show')
    args, _ = server.cli.parse_known_args()
    if not os.path.isfile(args.sww):
        sys.exit('anuga-web-viewer: no such file: %s' % args.sww)
    build(server, args.sww)
    server.start()


if __name__ == '__main__':
    main()
