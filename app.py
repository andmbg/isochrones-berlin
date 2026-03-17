import os

import dash_leaflet as dl
from dash import Dash, Input, Output, callback, dcc, html, no_update
import dash_mantine_components as dmc
import requests

from src.bvg import fetch_reachable_stops, nearest_stop
from src import cache
from src.plotting import make_layers, MAX_DURATION

app = Dash(__name__, url_base_pathname=os.getenv("DASH_URL_PREFIX", "/"))

_TILE_LIGHT = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
_TILE_DARK = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    ' &copy; <a href="https://carto.com/attributions">CARTO</a>'
)

def _legend():
    """
    Four adjacent rectangles representing the three isochrone bands plus the
    uncovered area (> 45 min).  Labels 15 / 30 / 45 sit above the shared edges.
    """
    rect_w, rect_h = 42, 14   # pixels

    # (border colour, fill colour) matching the bands in src/plotting.py
    bands = [
        ("#1a9641", "rgba(26,150,65,0.25)"),
        ("#d0c721", "rgba(208,199,33,0.25)"),
        ("#fdc461", "rgba(253,196,97,0.25)"),
    ]

    def rect(border, fill, left_border=True):
        return html.Div(style={
            "width": rect_w, "height": rect_h, "boxSizing": "border-box",
            "background": fill,
            "borderTop":    f"1.5px solid {border}",
            "borderRight":  f"1.5px solid {border}",
            "borderBottom": f"1.5px solid {border}",
            "borderLeft":   f"1.5px solid {border}" if left_border else "none",
        })

    rects = [rect(b, f, left_border=(i == 0)) for i, (b, f) in enumerate(bands)]
    # rects.append(rect("#808080", "rgba(128,128,128,0.25)", left_border=False))

    labels = [
        html.Span(str(minutes) + "'", style={
            "position": "absolute",
            "top": "-13px",
            "left": f"{(i + 1) * rect_w}px",
            "transform": "translateX(-50%)",
            "fontSize": "10px",
            "lineHeight": "1",
        })
        for i, minutes in enumerate([15, 30, 45])
    ]

    return html.Div(
        style={"position": "relative", "marginTop": "10px"},
        children=[*labels, html.Div(style={"display": "flex"}, children=rects)],
    )


app.layout = dmc.MantineProvider(
    id="mantine-provider",
    children=[
        dl.Map(
            id="map",
            center=[52.52, 13.405],
            zoom=13,
            children=[
                dl.TileLayer(id="tile-layer", url=_TILE_LIGHT, attribution=_ATTRIBUTION),
                dl.LayerGroup(id="stations-layer"),
            ],
            style={
                "position": "fixed",
                "inset": "0",
                "width": "100vw",
                "height": "100vh",
                "zIndex": 0,
            },
        ),
        # Controls panel
        dmc.Paper(
            dmc.Stack(
                [
                    dmc.Title("Isochrones Dashboard", order=4),
                    _legend(),
                    dmc.Switch(
                        id="color-scheme-toggle",
                        onLabel="🌙",
                        offLabel="☀️",
                        size="md",
                        checked=False,
                    ),
                    dmc.Group(
                        [
                            html.Div(
                                id="spinner",
                                className="spinner",
                                style={"display": "none"},
                            ),
                            dmc.Text(id="loading-text", size="xs", c="blue", mih=14),
                        ],
                        gap="xs",
                        align="center",
                    ),
                ],
                gap="xs",
                align="center",
            ),
            shadow="md",
            radius="md",
            p="md",
            style={
                "position": "fixed",
                "top": 10,
                "left": 50,
                "zIndex": 1000,
                # "minWidth": 300,
                "background-color": "#88888828",
                "border": "2px solid #88888888"
            },
        ),
        # Hint overlay — hidden after first click
        dmc.Paper(
            dmc.Text("Auf den Startort klicken", size="sm", fw=500),
            id="hint-overlay",
            shadow="sm",
            radius="md",
            p="sm",
            style={
                "position": "fixed",
                "top": "30%",
                "left": "50%",
                "transform": "translateX(-50%)",
                "zIndex": 1000,
                "pointerEvents": "none",

                "boxShadow": "10px 10px 80px rgba(0,0,0, .6)"
            },
        ),
        dcc.Store(id="stations-store"),
        dcc.Store(id="pending-30"),
        dcc.Store(id="pending-60"),
        dcc.Store(id="api-error"),
        dmc.Modal(
            id="error-modal",
            title="API Error",
            children=dmc.Text(
                "The BVG API returned a server error (500). Please try again later.",
                size="sm",
            ),
        ),
    ],
)


_SHOW = {"display": "inline-block"}
_HIDE = {"display": "none"}


@callback(
    Output("error-modal", "opened"),
    Input("api-error", "data"),
)
def show_error_modal(error):
    return bool(error)


@callback(
    Output("stations-store", "data"),
    Output("pending-30", "data"),
    Output("loading-text", "children"),
    Output("spinner", "style"),
    Output("api-error", "data"),
    Output("hint-overlay", "style"),
    Input("map", "clickData"),
)
def on_map_click(click_data):
    if not click_data:
        return None, None, "", _HIDE, None, no_update
    lat = click_data["latlng"]["lat"]
    lng = click_data["latlng"]["lng"]
    try:
        stop = nearest_stop(lat, lng)
    except requests.exceptions.HTTPError:
        return no_update, no_update, "", _HIDE, True, _HIDE
    origin = {**stop, "duration": 0, "origin": True}

    cached = cache.get(stop["id"])
    if cached is not None:
        return [origin, *cached], None, "", _HIDE, None, _HIDE

    stops_15 = fetch_reachable_stops(stop["lat"], stop["lng"], stop["name"], max_duration=15)
    return [origin, *stops_15], stop, "Loading 30 min radius...", _SHOW, None, _HIDE


@callback(
    Output("stations-store", "data", allow_duplicate=True),
    Output("pending-60", "data"),
    Output("loading-text", "children", allow_duplicate=True),
    Output("spinner", "style", allow_duplicate=True),
    Output("api-error", "data", allow_duplicate=True),
    Input("pending-30", "data"),
    prevent_initial_call=True,
)
def load_30(stop):
    if not stop:
        return no_update, no_update, no_update, no_update, no_update
    try:
        stops_30 = fetch_reachable_stops(stop["lat"], stop["lng"], stop["name"], max_duration=30)
    except requests.exceptions.HTTPError:
        return no_update, None, "", _HIDE, True
    origin = {**stop, "duration": 0, "origin": True}
    return [origin, *stops_30], stop, "Loading 60 min radius...", _SHOW, None


@callback(
    Output("stations-store", "data", allow_duplicate=True),
    Output("loading-text", "children", allow_duplicate=True),
    Output("spinner", "style", allow_duplicate=True),
    Output("api-error", "data", allow_duplicate=True),
    Input("pending-60", "data"),
    prevent_initial_call=True,
)
def load_60(stop):
    if not stop:
        return no_update, no_update, no_update, no_update
    try:
        stops_60 = fetch_reachable_stops(stop["lat"], stop["lng"], stop["name"], max_duration=MAX_DURATION)
    except requests.exceptions.HTTPError:
        return no_update, "", _HIDE, True
    cache.set(stop["id"], stops_60)
    origin = {**stop, "duration": 0, "origin": True}
    return [origin, *stops_60], "", _HIDE, None


@callback(
    Output("stations-layer", "children"),
    Input("stations-store", "data"),
)
def plot_stations(stops):
    return make_layers(stops)


@callback(
    Output("tile-layer", "url"),
    Output("mantine-provider", "forceColorScheme"),
    Input("color-scheme-toggle", "checked"),
)
def toggle_color_scheme(checked):
    return (_TILE_DARK if checked else _TILE_LIGHT), ("dark" if checked else "light")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
