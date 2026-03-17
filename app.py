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
                    dmc.Group(
                        [
                            dmc.Title("Isochrones Dashboard", order=4),
                            dmc.Switch(
                                id="color-scheme-toggle",
                                label="Dark mode",
                                size="sm",
                                checked=False,
                            ),
                        ],
                        justify="space-between",
                        align="center",
                    ),
                    dmc.Text(id="click-coords", c="dimmed", size="xs"),
                    dmc.Text(id="click-address", c="dimmed", size="xs"),
                    dmc.Group(
                        [
                            html.Div(
                                id="spinner",
                                className="spinner",
                                style={"display": "none"},
                            ),
                            dmc.Text(id="loading-text", size="xs", c="blue"),
                        ],
                        gap="xs",
                        align="center",
                    ),
                ],
                gap="xs",
            ),
            shadow="md",
            radius="md",
            p="md",
            style={
                "position": "fixed",
                "top": 10,
                "left": 50,
                "zIndex": 1000,
                "minWidth": 300,
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
    Output("click-coords", "children"),
    Output("click-address", "children"),
    Output("stations-store", "data"),
    Output("pending-30", "data"),
    Output("loading-text", "children"),
    Output("spinner", "style"),
    Output("api-error", "data"),
    Input("map", "clickData"),
)
def on_map_click(click_data):
    if not click_data:
        return "Klicke auf die Karte, um Koordinaten zu sehen.", "", None, None, "", _HIDE, None
    lat = click_data["latlng"]["lat"]
    lng = click_data["latlng"]["lng"]
    try:
        stop = nearest_stop(lat, lng)
    except requests.exceptions.HTTPError:
        return no_update, no_update, no_update, no_update, "", _HIDE, True
    coords = f"Lat: {stop['lat']:.5f}  |  Lng: {stop['lng']:.5f}"
    origin = {**stop, "duration": 0, "origin": True}

    cached = cache.get(stop["id"])
    if cached is not None:
        return coords, stop["name"], [origin, *cached], None, "", _HIDE, None

    stops_15 = fetch_reachable_stops(stop["lat"], stop["lng"], stop["name"], max_duration=15)
    return coords, stop["name"], [origin, *stops_15], stop, "Loading 30 min radius...", _SHOW, None


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
