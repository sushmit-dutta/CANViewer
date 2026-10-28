"""Cursor value lookup and the floating readout panels."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from dash import html

from canviewer.data import LogData
from canviewer.figures import PALETTE

# Up to this many cursors at once; adding another drops the oldest.
CURSOR_COLORS = ["#f6c90e", "#00d4ff", "#ff7849", "#f472b6", "#48bb78"]

# A reading older than this is annotated with its age, so a value that has not
# been refreshed near the cursor is not mistaken for a current one.
STALE_AFTER_NS = 1_000_000_000


@dataclass(frozen=True)
class Reading:
    signal: str
    color: str
    text: str
    numeric: Optional[float]


def _format_value(value, choices: Optional[Dict[int, str]]) -> tuple:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value), None
    if choices:
        label = choices.get(int(num)) if num == int(num) else None
        if label is not None:
            return f"{label} ({num:.6g})", num
    return f"{num:.6g}", num


def _format_age(delta_ns: int) -> str:
    return f"  ({delta_ns / 1e9:+.3f}s)" if abs(delta_ns) >= STALE_AFTER_NS else ""


def readings_at(frame: Dict, data: LogData, cursor_ns: int) -> List[Reading]:
    """Each signal's most recent sample at or before `cursor_ns`.

    Numeric signals are listed highest first, then non-numeric ones. A signal
    with no sample yet shows an em dash.
    """
    colors = frame.get("colors", {})
    hidden = set(frame.get("hidden", []))
    rows: List[Reading] = []
    for i, sig in enumerate(frame["signals"]):
        if sig in hidden:
            continue
        color = colors.get(sig) or PALETTE[i % len(PALETTE)]
        series = data.series(sig)
        if series is None or not series.ns.size:
            continue
        idx = int(np.searchsorted(series.ns, cursor_ns, side="right")) - 1
        if idx < 0:
            rows.append(Reading(sig, color, "—", None))
            continue
        text, num = _format_value(series.values[idx], data.choices(sig))
        rows.append(Reading(sig, color, text + _format_age(cursor_ns - int(series.ns[idx])), num))
    numeric = sorted((r for r in rows if r.numeric is not None), key=lambda r: -r.numeric)
    return numeric + [r for r in rows if r.numeric is None]


def cursor_label(data: LogData, cursor_ns: int) -> str:
    ts = pd.to_datetime(cursor_ns, unit="ns", utc=True).tz_convert(data.tz)
    return ts.strftime("%H:%M:%S.%f")[:-3]


def cursor_panels(frame: Dict, data: LogData, cursors: List[Dict]) -> List:
    """One independently draggable readout panel per cursor."""
    if not frame["signals"]:
        return []
    panels = []
    for n, cursor in enumerate(cursors):
        cursor_ns = data.local_to_ns(cursor.get("x", ""))
        if cursor_ns is None:
            continue
        color = cursor.get("color", CURSOR_COLORS[0])
        rows = [
            html.Div(
                [
                    html.Span("■", className="cp-swatch", style={"color": r.color}),
                    html.Span(r.signal, className="cp-name", title=r.signal),
                    html.Span(r.text, className="cp-value"),
                ],
                className="cp-row",
            )
            for r in readings_at(frame, data, cursor_ns)
        ]
        header = html.Div(
            [
                html.Span("⠿ ", className="cp-grip"),
                html.Span("●", style={"color": color}),
                html.Span(cursor_label(data, cursor_ns), className="cp-time"),
            ],
            className="cursor-drag-handle",
            style={"borderTop": f"3px solid {color}"},
        )
        panels.append(
            html.Div(
                [header, *rows],
                className="cursor-float-panel",
                # Stable key: the client restores a dragged panel's position
                # across re-renders by matching on it.
                **{"data-panel-key": f"{frame['id']}:{cursor.get('id', n)}"},
                style={"right": f"{8 + n * 215}px"},
            )
        )
    return panels


def add_cursor(cursors: List[Dict], x: str) -> List[Dict]:
    """Append a cursor at `x`, evicting the oldest once all colours are in use."""
    current = list(cursors or [])
    if len(current) >= len(CURSOR_COLORS):
        current = current[1:]
    used = {c.get("color") for c in current}
    color = next(c for c in CURSOR_COLORS if c not in used)
    return current + [{"id": uuid.uuid4().hex[:6], "x": x, "color": color}]
