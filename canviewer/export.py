"""Standalone HTML report of the frames currently on screen."""

from __future__ import annotations

from html import escape
from typing import Dict, List, Optional

import pandas as pd
import plotly.io as pio

from canviewer.cursors import CURSOR_COLORS, cursor_label, readings_at
from canviewer.data import LogData
from canviewer.figures import frame_figure, theme_colors


def _cursor_table(frame: Dict, data: LogData, cursors: List[Dict]) -> str:
    """One column per cursor, one row per visible signal."""
    columns = []  # (time label, colour, {signal: text})
    for cursor in cursors:
        ns = data.local_to_ns(cursor.get("x", ""))
        if ns is None:
            continue
        values = {r.signal: r.text for r in readings_at(frame, data, ns)}
        columns.append((cursor_label(data, ns), cursor.get("color", CURSOR_COLORS[0]), values))
    signals = [s for s in frame["signals"] if s not in set(frame.get("hidden", []))]
    if not columns or not signals:
        return ""

    colors = frame.get("colors", {})
    head = "".join(
        f'<th style="border-bottom:2px solid {c};text-align:left;">{escape(label)}</th>'
        for label, c, _ in columns
    )
    body = "".join(
        f'<tr><td style="color:{colors.get(sig, "inherit")};white-space:nowrap;">{escape(sig)}</td>'
        + "".join(f"<td>{escape(vals.get(sig, ''))}</td>" for _, _, vals in columns)
        + "</tr>"
        for sig in signals
    )
    return f"<table><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_export_html(
    frames: List[Dict],
    data: LogData,
    cursors: Optional[List[Dict]],
    theme: Optional[str],
) -> str:
    """Each non-empty frame as an interactive plot plus its cursor value table."""
    cursors = cursors or []
    generated = pd.Timestamp.now(tz=data.tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    parts = [f"<h2>{escape(data.title)}</h2>", f'<p class="meta">Exported {escape(generated)}</p>']

    first = True
    for frame in frames:
        if not frame["signals"]:
            continue
        fig = frame_figure(frame, data, theme, cursors)
        fig.update_layout(height=360, margin=dict(l=60, r=20, t=20, b=30))
        parts.append(
            pio.to_html(
                fig,
                full_html=False,
                include_plotlyjs="cdn" if first else False,
                config={"displaylogo": False},
            )
        )
        first = False
        parts.append(_cursor_table(frame, data, cursors))
        parts.append("<hr>")

    t = theme_colors(theme)
    style = (
        f"body{{background:{t['paper']};color:{t['font']};font-family:monospace;padding:16px}}"
        ".meta{color:#888}table{border-collapse:collapse;font-size:11px;margin:4px 0 14px}"
        "td,th{padding:2px 10px;border-bottom:1px solid rgba(128,128,128,.2)}"
        "hr{border:0;border-top:1px solid rgba(128,128,128,.3);margin:18px 0}"
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{escape(data.title)} export</title><style>{style}</style></head>"
        f"<body>{''.join(parts)}</body></html>"
    )
