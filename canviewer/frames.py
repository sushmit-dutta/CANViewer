"""Frame state (a list of plain dicts) and the operations on it.

A frame is ``{"id", "signals": [...], "hidden": [...], "colors": {sig: hex}}``.
Layout state that must not trigger a re-render (height, zoom) lives in its own
stores, not here.
"""

from __future__ import annotations

import json
import uuid
from typing import Dict, Iterable, List, Optional, Tuple

from canviewer.figures import next_color

Frame = Dict
Op = Tuple  # ("replace", index) | ("append",) | ("delete", index)


def new_frame() -> Frame:
    return {"id": uuid.uuid4().hex[:8], "signals": [], "hidden": [], "colors": {}}


def add_signals(frames: List[Frame], fid: str, names: Iterable[str]) -> List[Frame]:
    """Append `names` to frame `fid` (skipping ones already there)."""
    out = []
    for f in frames:
        if f["id"] != fid:
            out.append(f)
            continue
        signals = list(f["signals"])
        colors = dict(f.get("colors", {}))
        for name in names:
            if name not in signals:
                signals.append(name)
                colors[name] = next_color(list(colors.values()))
        out.append({**f, "signals": signals, "colors": colors})
    return out


def remove_signal(frames: List[Frame], fid: str, name: str) -> List[Frame]:
    out = []
    for f in frames:
        if f["id"] == fid:
            colors = {k: v for k, v in f.get("colors", {}).items() if k != name}
            f = {
                **f,
                "signals": [s for s in f["signals"] if s != name],
                "hidden": [s for s in f.get("hidden", []) if s != name],
                "colors": colors,
            }
        out.append(f)
    return out


def remove_frame(frames: List[Frame], fid: str) -> List[Frame]:
    return [f for f in frames if f["id"] != fid]


def toggle_hidden(frames: List[Frame], fid: str, name: str) -> List[Frame]:
    out = []
    for f in frames:
        if f["id"] == fid:
            hidden = list(f.get("hidden", []))
            hidden.remove(name) if name in hidden else hidden.append(name)
            f = {**f, "hidden": hidden}
        out.append(f)
    return out


def move_frame(frames: List[Frame], from_fid: str, to_fid: str) -> List[Frame]:
    """Move `from_fid` to the position currently held by `to_fid`."""
    ids = [f["id"] for f in frames]
    if from_fid == to_fid or from_fid not in ids or to_fid not in ids:
        return frames
    out = list(frames)
    out.insert(ids.index(to_fid), out.pop(ids.index(from_fid)))
    return out


def fingerprint(frame: Frame) -> List:
    """What determines how a frame's card looks (excludes height and zoom).

    Built only from JSON-native values so it survives a round trip through a
    ``dcc.Store`` and still compares equal.
    """
    return [
        frame["id"],
        "\x1f".join(frame["signals"]),
        "\x1f".join(frame.get("hidden", [])),
        json.dumps(frame.get("colors", {}), sort_keys=True),
    ]


def diff(previous: Optional[List[List]], frames: List[Frame]) -> Optional[List[Op]]:
    """Minimal DOM operations to turn the rendered frames into `frames`.

    Returns ``None`` when a full rebuild is the only safe option (first render,
    reorder), otherwise a possibly empty list of ops. Rebuilding every card on
    every change is what made add/remove/resize feel unstable, so the common
    cases touch exactly one card.
    """
    new = [fingerprint(f) for f in frames]
    if previous is None:
        return None
    prev_ids = [p[0] for p in previous]
    new_ids = [n[0] for n in new]

    if prev_ids == new_ids:
        return [("replace", i) for i, (p, n) in enumerate(zip(previous, new)) if p != n]
    if new_ids[: len(prev_ids)] == prev_ids and len(new_ids) == len(prev_ids) + 1:
        ops: List[Op] = [("replace", i) for i, (p, n) in enumerate(zip(previous, new)) if p != n]
        return ops + [("append",)]
    if len(prev_ids) == len(new_ids) + 1:
        for i in range(len(prev_ids)):
            if prev_ids[:i] + prev_ids[i + 1 :] == new_ids:
                kept = previous[:i] + previous[i + 1 :]
                ops = [("replace", j) for j, (p, n) in enumerate(zip(kept, new)) if p != n]
                # Replacements are indexed after the delete.
                return [("delete", i)] + ops
    return None
