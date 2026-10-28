"""Signal sidebar: collapsible message groups, or ranked search results."""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from dash import html

from canviewer.data import LogData, SignalInfo
from canviewer.search import SearchIndex

# Cap on rendered search rows; the rest are reachable by refining the query.
MAX_RESULTS = 200
# "Add all matches" is offered only when dragging that many is sensible.
MAX_DRAG_ALL = 64


def _signal_row(info: SignalInfo, with_context: bool) -> html.Div:
    children: List = [html.Div(info.name, className="sig-name")]
    if with_context:
        detail = info.message + (f" · {info.unit}" if info.unit else "")
        children.append(html.Div(detail, className="sig-context"))
    return html.Div(
        children,
        className="sig-item",
        draggable="true",
        title="\n".join(p for p in (info.name, info.message, info.unit, info.comment) if p),
        **{"data-signal": info.name},
    )


def _group_chip(label: str, names: List[str], tooltip: str) -> html.Div:
    return html.Div(
        label,
        className="sig-chip",
        draggable="true",
        title=tooltip,
        **{"data-signals": json.dumps(names)},
    )


def _message_group(message: str, names: List[str], catalog: Dict[str, SignalInfo]) -> html.Details:
    return html.Details(
        [
            html.Summary(
                [
                    html.Span("▶", className="caret"),
                    html.Div(
                        [
                            html.Span(message, className="msg-name", title=message),
                            html.Span(f"⊞{len(names)}", className="msg-count"),
                        ],
                        className="msg-drag",
                        draggable="true",
                        title=f"Drag to add all {len(names)} signals of {message}",
                        **{"data-signals": json.dumps(names)},
                    ),
                ],
                className="msg-summary",
            ),
            html.Div([_signal_row(catalog[n], False) for n in names], className="msg-body"),
        ],
        className="msg-group",
    )


def browse_items(data: LogData) -> List:
    """No query: every message as a collapsible group."""
    return [_message_group(m, names, data.catalog) for m, names in data.messages.items()]


def search_items(data: LogData, index: SearchIndex, query: str):
    """Query: (children, status line)."""
    result = index.search(query, limit=MAX_RESULTS)
    items: List = []

    if result.messages:
        for msg in result.messages:
            names = data.messages.get(msg, [])
            items.append(
                _group_chip(f"⊞ {msg} ({len(names)})", names, f"Drag all {len(names)} signals of {msg}")
            )

    shown = result.signals
    if 1 < len(shown) <= MAX_DRAG_ALL and result.total <= MAX_DRAG_ALL:
        items.append(
            _group_chip(
                f"⊞ all {len(shown)} matches",
                [s.name for s in shown],
                f"Drag all {len(shown)} matching signals",
            )
        )
    items.extend(_signal_row(info, True) for info in shown)

    if not items:
        return [html.Div("no matches", className="sig-empty")], "no matches"

    status = f"{result.total} signal{'s' if result.total != 1 else ''}"
    if result.messages:
        status += f", {len(result.messages)} message{'s' if len(result.messages) != 1 else ''}"
    if result.fuzzy:
        status = f"no exact match — {status} by fuzzy name match"
    if result.total > len(shown):
        status += f" · showing first {len(shown)}, refine to narrow"
    return items, status
