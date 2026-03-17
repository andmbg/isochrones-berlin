"""
Converts transit stop data (lat, lng, travel_time) into Dash Leaflet map layers:
  - Filled isochrone bands (GeoJSON polygons) at 0-15, 15-30, 30-45 min
  - Omitting 60 min makes the outer contour a bit less arbitrary
  - Scatter markers for individual stops

The isochrone bands are produced in three steps:
  1. Interpolate the irregularly-spaced stop durations onto a regular grid
     (scipy griddata uses Delaunay triangulation under the hood).
  2. Compute filled contours with matplotlib — we never display the figure,
     we just extract the polygon paths from it.
  3. Convert those paths to GeoJSON so Dash Leaflet can render them.
"""

import matplotlib
matplotlib.use("Agg")   # no display needed; we only extract path data

import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import griddata

import dash_leaflet as dl


MAX_DURATION = 60             # minutes — colour scale and outermost isochrone
LEVELS = [0, 15, 30, 45, 60] # isochrone boundaries in minutes
GRID_SIZE = 200               # interpolation grid resolution (points per axis)

# Fill colour per band, fast → slow:
_BAND_COLOURS = ["#1a9641", "#d0c721", "#fdc461", "#d7191c"]


# ── Public entry point ───────────────────────────────────────────────────────

def make_layers(stops: list[dict]) -> list:
    """
    Given a list of stop dicts (each with lat, lng, duration; origin stops have
    origin=True), return a list of Dash Leaflet layer objects ready to be used
    as children of a LayerGroup.

    Returns isochrone bands first (bottom), markers on top.
    """
    if not stops:
        return []

    origin  = next((s for s in stops if s.get("origin")), None)
    regular = [s for s in stops if not s.get("origin")]

    layers = []
    if len(regular) >= 4:           # need enough points to triangulate
        layers += _isochrone_bands(regular)
    layers += [
        dl.CircleMarker(
            center=[s["lat"], s["lng"]],
            radius=3,
            color="rgb(70,168,255)",
            fillColor="rgb(50, 120, 200)",
            fillOpacity=0.6,
            weight=1,
            children=dl.Tooltip(f"{s['name']} ({s['duration']} min)"),
        )
        for s in regular
    ]
    if origin:
        layers.append(_origin_marker(origin))
    return layers


# ── Isochrone contour bands ──────────────────────────────────────────────────

def _isochrone_bands(stops: list[dict]) -> list:
    """
    Interpolate travel time across a regular grid, then extract filled contour
    polygons and return them as dl.GeoJSON layers, one per time band.
    """
    lngs      = np.array([s["lng"]      for s in stops])
    lats      = np.array([s["lat"]      for s in stops])
    durations = np.array([s["duration"] for s in stops], dtype=float)

    # Step 1: regular lat/lng grid covering the extent of the stops
    grid_lng, grid_lat = np.meshgrid(
        np.linspace(lngs.min(), lngs.max(), GRID_SIZE),
        np.linspace(lats.min(), lats.max(), GRID_SIZE),
    )

    # Step 2: interpolate scattered stop durations onto the grid.
    # Outside the convex hull of the input stops, griddata returns NaN —
    # those areas will simply not be covered by any contour band.
    grid_z = griddata(
        points=np.column_stack([lngs, lats]),
        values=durations,
        xi=(grid_lng, grid_lat),
        method="linear",
    )
    grid_z = np.ma.masked_invalid(grid_z)   # mask NaN so contourf ignores them

    # Steps 3 & 4: for each time band, contour a binary mask (1 = in band, 0 = not).
    # One contourf per band keeps path extraction simple: get_paths() is the
    # stable public API and returns exactly the paths for that single band.
    layers = []
    for (level_min, level_max), colour in zip(zip(LEVELS[:-2], LEVELS[1:-1]), _BAND_COLOURS):
        in_band = np.ma.masked_where(
            np.ma.getmaskarray(grid_z),
            ((grid_z >= level_min) & (grid_z < level_max)).astype(float),
        )
        fig, ax = plt.subplots()
        cs = ax.contourf(grid_lng, grid_lat, in_band, levels=[0.5, 1.5])
        plt.close(fig)

        geojson = _paths_to_geojson(cs.get_paths())
        layers.append(
            dl.GeoJSON(
                data=geojson,
                style={
                    "fillColor": colour,
                    "fillOpacity": 0.25,
                    "color": colour,
                    "weight": 1.5,
                    "interactive": False,
                },
            )
        )
    return layers


def _paths_to_geojson(level_paths: list) -> dict:
    """
    Convert a list of matplotlib Path objects (one contour band) to a GeoJSON
    FeatureCollection.  Each Path becomes one Polygon Feature.

    A single Path may describe a polygon with holes: to_polygons() splits it
    at MOVETO codes, returning [outer_ring, hole1, hole2, ...].
    GeoJSON Polygon coordinates use the same layout.
    """
    features = []
    for path in level_paths:
        rings = path.to_polygons()      # list of Nx2 arrays, one per ring
        if not rings:
            continue

        geojson_rings = []
        for ring in rings:
            coords = ring.tolist()
            if coords[0] != coords[-1]:     # GeoJSON rings must be closed
                coords.append(coords[0])
            geojson_rings.append(coords)

        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": geojson_rings},
            "properties": {},
        })

    return {"type": "FeatureCollection", "features": features}


# ── Origin marker ────────────────────────────────────────────────────────────

def _origin_marker(origin: dict) -> dl.CircleMarker:
    """Blue pin marking the stop the isochrones radiate from."""
    return dl.CircleMarker(
        center=[origin["lat"], origin["lng"]],
        radius=10,
        color="white",
        fillColor="rgb(30,100,255)",
        fillOpacity=1.0,
        weight=2,
        children=dl.Tooltip(origin["name"]),
    )
