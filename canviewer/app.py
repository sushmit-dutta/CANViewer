"""The Dash application: layout and callbacks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import dash
import pandas as pd
from dash import (
    ALL,
    ClientsideFunction,
    Input,
    Output,
    Patch,
    State,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
)

from canviewer import frames as fr
from canviewer.cards import frame_card
from canviewer.cursors import add_cursor, cursor_panels
from canviewer.data import LogData
from canviewer.export import build_export_html
from canviewer.figures import cursor_shape, frame_traces, theme_colors
from canviewer.search import SearchIndex
from canviewer.sidebar import browse_items, search_items

APP_NAME = "CANViewer"
MIN_FRAME_HEIGHT = 200
MAX_FRAME_HEIGHT = 4000


def _layout(data: LogData, sidebar_children: List) -> html.Div:
    return html.Div(
        id="app-root",
        children=[
            dcc.Store(id="frames-store", data=[fr.new_frame()]),
            # Kept out of frames-store on purpose: changing any of these must
            # not re-render the frame cards.
            dcc.Store(id="zoom-store", data=None),
            dcc.Store(id="heights-store", data={}),
            dcc.Store(id="rendered-store", data=None),
            dcc.Store(id="cursor-mode", data=False),
            dcc.Store(id="cursors", data=[]),
            dcc.Store(id="theme", data="dark"),
            # Written by assets/interactions.js via dash_clientside.set_props.
            dcc.Store(id="drop-store"),
            dcc.Store(id="reorder-store"),
            dcc.Store(id="resize-store"),
            dcc.Store(id="cursor-key-store"),
            html.Div(id="client-sync", hidden=True),
            dcc.Download(id="download-html"),
            html.Div(
                className="navbar",
                children=[
                    html.Span(APP_NAME, className="brand"),
                    html.Span(data.title, className="log-title", title=data.title),
                    html.Div(className="spacer"),
                    html.Button("🌙", id="theme-btn", n_clicks=0, className="btn", title="Toggle light/dark theme"),
                    html.Button("✕ Clear cursors", id="clear-cursors-btn", n_clicks=0,
                                className="btn btn-danger", hidden=True),
                    html.Button("⊕ Cursor", id="cursor-btn", n_clicks=0, className="btn",
                                title="Click a frame to place a cursor (or press . at the pointer)"),
                    html.Button("+ Add frame", id="add-frame-btn", n_clicks=0, className="btn btn-primary"),
                    html.Button("📄 Export HTML", id="export-html-btn", n_clicks=0, className="btn",
                                title="Export frames, cursors and values as a standalone HTML report"),
                ],
            ),
            html.Div(
                className="body",
                children=[
                    html.Div(
                        className="sidebar",
                        children=[
                            html.Div(f"SIGNALS ({len(data.catalog)})", className="sidebar-title"),
                            dcc.Input(
                                id="sig-search",
                                type="search",
                                debounce=False,
                                autoComplete="off",
                                placeholder="name, message, node, unit, 0xID…",
                                className="search-box",
                            ),
                            html.Div(
                                "Several words match together · * and ? are wildcards",
                                id="search-status",
                                className="search-status",
                            ),
                            html.Div(sidebar_children, id="sig-list", className="sig-list"),
                        ],
                    ),
                    html.Div(id="plot-area", className="plot-area"),
                ],
            ),
        ],
    )


def create_app(data: LogData) -> dash.Dash:
    """Build the explorer for an already-loaded log."""
    app = dash.Dash(
        __name__,
        assets_folder=str(Path(__file__).parent / "assets"),
        title=f"{APP_NAME} · {data.title}",
        suppress_callback_exceptions=True,
    )
    index = SearchIndex(data.catalog.values())
    valid_signals = set(data.catalog)
    app.layout = _layout(data, browse_items(data))

    # ── sidebar ──────────────────────────────────────────────────────────────

    @app.callback(
        Output("sig-list", "children"),
        Output("search-status", "children"),
        Input("sig-search", "value"),
    )
    def filter_signals(query: Optional[str]):
        if not (query or "").strip():
            return browse_items(data), "Several words match together · * and ? are wildcards"
        return search_items(data, index, query)

    # ── frame state ──────────────────────────────────────────────────────────

    @app.callback(
        Output("frames-store", "data"),
        Input("drop-store", "data"),
        Input("reorder-store", "data"),
        Input("add-frame-btn", "n_clicks"),
        Input({"type": "rm-sig", "fid": ALL, "sig": ALL}, "n_clicks"),
        Input({"type": "rm-frame", "fid": ALL}, "n_clicks"),
        Input({"type": "legend-item", "fid": ALL, "sig": ALL}, "n_clicks"),
        State("frames-store", "data"),
        prevent_initial_call=True,
    )
    def update_frames(drop, reorder, _add, _rm_sig, _rm_frame, _legend, frames):
        tid = ctx.triggered_id
        value = ctx.triggered[0]["value"] if ctx.triggered else None
        # A button that merely mounted (n_clicks still 0) also fires this
        # callback; only a real click or a JS event carries a truthy value.
        if not value:
            return no_update

        if tid == "add-frame-btn":
            return frames + [fr.new_frame()]
        if tid == "drop-store":
            names = [s for s in drop.get("sigs", []) if s in valid_signals]
            return fr.add_signals(frames, drop.get("fid"), names) if names else no_update
        if tid == "reorder-store":
            return fr.move_frame(frames, reorder.get("from"), reorder.get("to"))
        if isinstance(tid, dict):
            kind = tid.get("type")
            if kind == "rm-frame":
                return fr.remove_frame(frames, tid["fid"])
            if kind == "rm-sig":
                return fr.remove_signal(frames, tid["fid"], tid["sig"])
            if kind == "legend-item":
                return fr.toggle_hidden(frames, tid["fid"], tid["sig"])
        return no_update

    @app.callback(
        Output("heights-store", "data"),
        Input("resize-store", "data"),
        State("heights-store", "data"),
        prevent_initial_call=True,
    )
    def store_height(event, heights):
        try:
            fid, height = event["fid"], int(event["height"])
        except (TypeError, KeyError, ValueError):
            return no_update
        height = max(MIN_FRAME_HEIGHT, min(MAX_FRAME_HEIGHT, height))
        return {**(heights or {}), fid: height}

    @app.callback(
        Output("plot-area", "children"),
        Output("rendered-store", "data"),
        Input("frames-store", "data"),
        State("rendered-store", "data"),
        State("cursors", "data"),
        State("theme", "data"),
        State("zoom-store", "data"),
        State("heights-store", "data"),
    )
    def render_frames(frames, rendered, cursors, theme, xrange, heights):
        """Render only the cards that changed; rebuild all on first load/reorder."""

        def card(i: int):
            f = frames[i]
            return frame_card(f, i, data, theme, cursors or [], xrange, (heights or {}).get(f["id"]))

        fingerprints = [fr.fingerprint(f) for f in frames]
        ops = fr.diff(rendered, frames)
        if ops is None:
            return [card(i) for i in range(len(frames))], fingerprints
        if not ops:
            return no_update, fingerprints

        patch = Patch()
        for op in ops:
            if op[0] == "delete":
                del patch[op[1]]
            elif op[0] == "replace":
                patch[op[1]] = card(op[1])
            elif op[0] == "append":
                patch.append(card(len(frames) - 1))
        return patch, fingerprints

    # ── cursors and theme ────────────────────────────────────────────────────

    @app.callback(
        Output("cursor-mode", "data"),
        Output("cursor-btn", "children"),
        Output("cursor-btn", "className"),
        Input("cursor-btn", "n_clicks"),
        State("cursor-mode", "data"),
        prevent_initial_call=True,
    )
    def toggle_cursor_mode(_, enabled):
        on = not enabled
        return on, "⊘ Cursor" if on else "⊕ Cursor", "btn btn-active" if on else "btn"

    @app.callback(
        Output("theme", "data"),
        Output("theme-btn", "children"),
        Input("theme-btn", "n_clicks"),
        State("theme", "data"),
        prevent_initial_call=True,
    )
    def toggle_theme(_, current):
        new = "light" if current == "dark" else "dark"
        return new, "☀️" if new == "light" else "🌙"

    # Sets data-theme on <html>, mirrors cursor mode onto <body> and tracks the
    # last hovered x for the "." shortcut (all in assets/interactions.js).
    clientside_callback(
        ClientsideFunction("canviewer", "sync"),
        Output("client-sync", "children"),
        Input("theme", "data"),
        Input({"type": "frame-graph", "fid": ALL}, "hoverData"),
        Input("cursor-mode", "data"),
    )

    @app.callback(
        Output("cursors", "data"),
        Output("clear-cursors-btn", "hidden"),
        Input({"type": "frame-graph", "fid": ALL}, "clickData"),
        Input("cursor-key-store", "data"),
        Input("clear-cursors-btn", "n_clicks"),
        State("cursor-mode", "data"),
        State("cursors", "data"),
        prevent_initial_call=True,
    )
    def manage_cursors(_clicks, key_event, _clear, cursor_mode, cursors):
        tid = ctx.triggered_id
        if tid == "clear-cursors-btn":
            return [], True
        if not cursor_mode:
            return no_update, no_update
        if tid == "cursor-key-store":
            x = (key_event or {}).get("x")
            return (add_cursor(cursors, x), False) if x else (no_update, no_update)
        for item in ctx.triggered:
            point = item.get("value")
            if isinstance(point, dict) and point.get("points"):
                return add_cursor(cursors, point["points"][0]["x"]), False
        return no_update, no_update

    @app.callback(
        Output({"type": "frame-graph", "fid": ALL}, "figure"),
        Output({"type": "cursor-panel", "fid": ALL}, "children"),
        Input("cursors", "data"),
        Input("theme", "data"),
        State("frames-store", "data"),
        prevent_initial_call=True,
    )
    def sync_cursors_and_theme(cursors, theme, frames):
        """Patch cursor lines, theme colours and readout panels in place."""
        t = theme_colors(theme)
        by_id = {f["id"]: f for f in frames}
        shapes = [cursor_shape(c["x"], c["color"]) for c in (cursors or []) if c.get("x")]
        figs, panels = [], []
        for out in ctx.outputs_list[0]:
            frame = by_id.get(out["id"]["fid"])
            if frame is None:
                figs.append(no_update)
                panels.append(no_update)
                continue
            p = Patch()
            p["layout"]["shapes"] = shapes
            p["layout"]["paper_bgcolor"] = t["paper"]
            p["layout"]["plot_bgcolor"] = t["plot"]
            p["layout"]["font"] = {"color": t["font"]}
            for axis in ("xaxis", "yaxis"):
                p["layout"][axis]["gridcolor"] = t["grid"]
                p["layout"][axis]["linecolor"] = t["grid"]
            figs.append(p)
            panels.append(cursor_panels(frame, data, cursors or []))
        return figs, panels

    @app.callback(
        Output({"type": "frame-graph", "fid": ALL}, "figure", allow_duplicate=True),
        Output("zoom-store", "data"),
        Input({"type": "frame-graph", "fid": ALL}, "relayoutData"),
        prevent_initial_call=True,
    )
    def sync_xaxis_zoom(relayouts):
        """Mirror an x-axis pan/zoom from the frame the user touched onto the rest."""
        output_ids = [o["id"]["fid"] for o in ctx.outputs_list[0]]
        unchanged = [no_update] * len(output_ids)
        tid = ctx.triggered_id
        if not isinstance(tid, dict):
            return unchanged, no_update

        source = tid["fid"]
        relayout = next(
            (r for i, r in zip(ctx.inputs_list[0], relayouts) if i["id"]["fid"] == source), None
        ) or {}
        autorange = relayout.get("xaxis.autorange") is True
        if not autorange and not ("xaxis.range[0]" in relayout and "xaxis.range[1]" in relayout):
            return unchanged, no_update
        xrange = None if autorange else [relayout["xaxis.range[0]"], relayout["xaxis.range[1]"]]

        patches = []
        for fid in output_ids:
            if fid == source:
                patches.append(no_update)
                continue
            p = Patch()
            p["layout"]["xaxis"]["autorange"] = autorange
            if not autorange:
                p["layout"]["xaxis"]["range"] = xrange
            patches.append(p)
        return patches, xrange

    @app.callback(
        Output({"type": "frame-graph", "fid": ALL}, "figure", allow_duplicate=True),
        Input("zoom-store", "data"),
        State("frames-store", "data"),
        prevent_initial_call=True,
    )
    def refresh_resolution(xrange, frames):
        """Swap in the samples for the new visible window (full-range when reset)."""
        by_id = {f["id"]: f for f in frames}
        out = []
        for o in ctx.outputs_list:
            frame = by_id.get(o["id"]["fid"])
            traces = frame_traces(frame, data, xrange) if frame and frame["signals"] else []
            if not traces:
                out.append(no_update)
                continue
            p = Patch()
            for i, tr in enumerate(traces):
                p["data"][i]["x"] = tr["x"].strftime("%Y-%m-%d %H:%M:%S.%f").tolist()
                p["data"][i]["y"] = tr["y"].tolist()
                if "customdata" in tr:
                    p["data"][i]["customdata"] = tr["customdata"].tolist()
            out.append(p)
        return out

    # ── export ───────────────────────────────────────────────────────────────

    @app.callback(
        Output("download-html", "data"),
        Input("export-html-btn", "n_clicks"),
        State("frames-store", "data"),
        State("cursors", "data"),
        State("theme", "data"),
        prevent_initial_call=True,
    )
    def export_html(_, frames, cursors, theme):
        content = build_export_html(frames, data, cursors, theme)
        stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        return dcc.send_string(content, filename=f"{Path(data.title).stem}_export_{stamp}.html")

    return app
