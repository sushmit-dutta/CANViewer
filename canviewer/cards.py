"""Dash components for one frame card."""

from __future__ import annotations

from typing import Dict, List, Optional

from dash import dcc, html

from canviewer.cursors import cursor_panels
from canviewer.data import LogData
from canviewer.figures import PALETTE, frame_figure


def _chip(frame_id: str, sig: str) -> html.Span:
    return html.Span(
        [
            sig,
            html.Button(
                "×",
                id={"type": "rm-sig", "fid": frame_id, "sig": sig},
                n_clicks=0,
                className="chip-x",
                title=f"Remove {sig}",
            ),
        ],
        className="sig-chip-inline",
    )


def _legend(frame: Dict) -> html.Div:
    hidden = set(frame.get("hidden", []))
    colors = frame.get("colors", {})
    items = [
        html.Span(
            ["● ", sig],
            id={"type": "legend-item", "fid": frame["id"], "sig": sig},
            n_clicks=0,
            className="legend-item" + (" is-hidden" if sig in hidden else ""),
            title=f"Click to {'show' if sig in hidden else 'hide'} {sig}",
            style={} if sig in hidden else {"color": colors.get(sig) or PALETTE[i % len(PALETTE)]},
        )
        for i, sig in enumerate(frame["signals"])
    ]
    return html.Div(html.Div(items, className="legend-row"), className="legend h-scroll")


def frame_card(
    frame: Dict,
    position: int,
    data: LogData,
    theme: Optional[str],
    cursors: List[Dict],
    xrange: Optional[List] = None,
    height: Optional[int] = None,
) -> html.Div:
    """Header, plot, legend and resize handle for one frame.

    `height` (px) comes from the heights store; without it the CSS default
    applies, so every card starts out the same size.
    """
    fid = frame["id"]
    return html.Div(
        className="frame-card",
        style={"height": f"{height}px"} if height else None,
        **{"data-frame-card": fid},
        children=[
            html.Div(
                className="frame-header",
                children=[
                    html.Span(
                        "⠿",
                        className="frame-grip",
                        draggable="true",
                        title="Drag to reorder frame",
                        **{"data-frame-drag": fid},
                    ),
                    html.Span(f"Frame {position + 1}", className="frame-title"),
                    html.Div([_chip(fid, s) for s in frame["signals"]], className="chip-row h-scroll"),
                    html.Button(
                        "✕",
                        id={"type": "rm-frame", "fid": fid},
                        n_clicks=0,
                        className="frame-close",
                        title="Remove frame",
                    ),
                ],
            ),
            html.Div(
                className="frame-plot",
                children=[
                    dcc.Graph(
                        id={"type": "frame-graph", "fid": fid},
                        figure=frame_figure(frame, data, theme, cursors, xrange),
                        config={
                            "displaylogo": False,
                            "responsive": True,
                            "scrollZoom": True,
                        },
                        style={"height": "100%"},
                    ),
                    # Pass-through overlay; each panel inside re-enables pointer events.
                    html.Div(
                        cursor_panels(frame, data, cursors),
                        id={"type": "cursor-panel", "fid": fid},
                        className="cursor-overlay",
                    ),
                ],
            ),
            _legend(frame),
            html.Div(className="frame-resize-handle", title="Drag to resize frame"),
        ],
    )
