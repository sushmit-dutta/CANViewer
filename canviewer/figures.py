"""Plotly figure construction for one frame. Pure functions of their inputs."""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import plotly.graph_objects as go

from canviewer.data import LogData
from canviewer.decimate import select

# Readable on both the dark and light themes.
PALETTE = [
    "#4e9af1", "#f28e2b", "#59c36a", "#e15759", "#b07aa1", "#edc948", "#17becf",
    "#ff9da7", "#9c755f", "#8cd17d", "#d37295", "#86bcb6", "#f1ce63", "#a0cbe8",
    "#ffbe7d", "#b6992d", "#499894", "#d4a6c8", "#79706e", "#bab0ac",
]

THEMES: Dict[str, Dict[str, str]] = {
    "dark": {"paper": "#1e2535", "plot": "#252f40", "grid": "#2d3748", "font": "#e2e8f0"},
    "light": {"paper": "#ffffff", "plot": "#fafafa", "grid": "#e2e8f0", "font": "#1a202c"},
}

# Above this many points in a frame, SVG scatter gets sluggish: switch to WebGL.
_WEBGL_POINT_THRESHOLD = 20_000
MARKER_SIZE = 4


def theme_colors(theme: Optional[str]) -> Dict[str, str]:
    return THEMES["light" if theme == "light" else "dark"]


def next_color(used: List[str]) -> str:
    """First palette colour not already used in the frame (cycles when full)."""
    for color in PALETTE:
        if color not in used:
            return color
    return PALETTE[len(used) % len(PALETTE)]


def _enum_labels(values: np.ndarray, choices: Dict[int, str]) -> np.ndarray:
    """Label for every sample, resolved once per distinct value."""
    labels = {}
    for v in np.unique(values):
        try:
            labels[v] = choices.get(int(v), str(v))
        except (TypeError, ValueError):
            labels[v] = str(v)
    return np.array([labels[v] for v in values], dtype=object)


def _placeholder(message: str, color: str, theme: Optional[str]) -> go.Figure:
    t = theme_colors(theme)
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=t["paper"],
        plot_bgcolor=t["plot"],
        margin=dict(l=50, r=10, t=10, b=10),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[
            dict(text=message, xref="paper", yref="paper", x=0.5, y=0.5,
                 showarrow=False, font=dict(color=color, size=12))
        ],
    )
    return fig


def _plotted(frame: Dict, data: LogData):
    """(signal, series) for the frame's signals that have samples."""
    pairs = [(s, data.series(s)) for s in frame["signals"]]
    return [(s, ser) for s, ser in pairs if ser is not None and ser.ns.size]


def frame_traces(frame: Dict, data: LogData, xrange: Optional[List] = None) -> List[Dict]:
    """x/y(/customdata) per plotted signal, reduced to the visible window.

    Same order as the figure's traces, so a zoom can patch them in place.
    """
    lo = hi = None
    if xrange:
        lo, hi = data.local_to_ns(str(xrange[0])), data.local_to_ns(str(xrange[1]))
    out = []
    for sig, ser in _plotted(frame, data):
        idx = select(ser.ns, ser.values, lo, hi)
        tr = {"x": data.local_times(ser.ns[idx]), "y": ser.values[idx]}
        choices = data.catalog[sig].choices
        if choices:
            tr["customdata"] = _enum_labels(tr["y"], choices)
        out.append(tr)
    return out


def cursor_shape(x: str, color: str) -> Dict:
    """Dashed vertical cursor line spanning the plot."""
    return {
        "type": "line", "x0": x, "x1": x, "y0": 0, "y1": 1, "yref": "paper",
        "layer": "above", "line": {"color": color, "width": 1.5, "dash": "dot"},
    }


def frame_figure(
    frame: Dict,
    data: LogData,
    theme: Optional[str],
    cursors: List[Dict],
    xrange: Optional[List] = None,
) -> go.Figure:
    """One frame: every signal drawn as discrete samples at its own timestamps.

    Samples are never joined or interpolated, so gaps in a signal's reporting
    (lost frames, a node going quiet) show up as gaps rather than as a line
    bridging them.
    """
    sigs = frame["signals"]
    if not sigs:
        return _placeholder("drag signals here", "#718096", theme)

    hidden = set(frame.get("hidden", []))
    colors = frame.get("colors", {})
    loaded = [(s, data.series(s)) for s in sigs]
    loaded = [(s, ser) for s, ser in loaded if ser is not None and ser.ns.size]
    if not loaded:
        return _placeholder("no samples for these signals in the log", "#fc8181", theme)

    traces = frame_traces(frame, data, xrange)
    use_gl = sum(len(tr["x"]) for tr in traces) > _WEBGL_POINT_THRESHOLD
    trace_cls = go.Scattergl if use_gl else go.Scatter

    fig = go.Figure()
    for i, ((sig, _), tr) in enumerate(zip(loaded, traces)):
        info = data.catalog[sig]
        color = colors.get(sig) or PALETTE[i % len(PALETTE)]
        unit = f" {info.unit}" if info.unit else ""
        kwargs = {}
        if info.choices:
            kwargs["customdata"] = tr["customdata"]
            kwargs["hovertemplate"] = "%{customdata} (%{y})<extra>" + sig + "</extra>"
        else:
            kwargs["hovertemplate"] = "%{y:.6g}" + unit + "<extra>" + sig + "</extra>"
        fig.add_trace(
            trace_cls(
                x=tr["x"],
                y=tr["y"],
                name=sig,
                mode="markers",
                marker=dict(color=color, size=MARKER_SIZE),
                visible=False if sig in hidden else True,
                **kwargs,
            )
        )

    t = theme_colors(theme)
    fig.update_layout(
        paper_bgcolor=t["paper"],
        plot_bgcolor=t["plot"],
        font={"color": t["font"]},
        showlegend=False,
        margin=dict(l=55, r=10, t=10, b=25),
        hovermode="x unified",
        shapes=[cursor_shape(c["x"], c["color"]) for c in cursors if c.get("x")],
        uirevision=frame["id"],
    )
    xaxis = dict(
        gridcolor=t["grid"], linecolor=t["grid"], showspikes=True,
        spikecolor="#4a5568", spikesnap="cursor", spikemode="across", spikethickness=1,
    )
    if xrange:
        # A rebuilt figure would otherwise snap back to autorange and lose the
        # zoom shared with the other frames.
        xaxis.update(range=xrange, autorange=False)
    fig.update_xaxes(**xaxis)
    fig.update_yaxes(gridcolor=t["grid"], linecolor=t["grid"], zerolinecolor=t["grid"])
    return fig
