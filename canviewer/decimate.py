"""Zoom-aware point reduction so big logs stay responsive.

The browser only ever receives the samples inside the visible window, capped
at ``MAX_POINTS`` per trace. When a window holds more, each time bucket keeps
its minimum and maximum sample, so spikes survive, and empty buckets stay
empty, so gaps survive. Zooming in re-selects from the raw samples, so detail
returns as the window narrows.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

MAX_POINTS = 4000


def select(
    ns: np.ndarray,
    values: np.ndarray,
    lo_ns: Optional[int],
    hi_ns: Optional[int],
    max_points: int = MAX_POINTS,
) -> np.ndarray:
    """Indices into `ns`/`values` to draw for the window [lo_ns, hi_ns]."""
    a = 0 if lo_ns is None else int(np.searchsorted(ns, lo_ns, side="left"))
    b = len(ns) if hi_ns is None else int(np.searchsorted(ns, hi_ns, side="right"))
    if b - a <= max_points:
        return np.arange(a, b)

    buckets = max(max_points // 2, 1)
    span = int(ns[b - 1] - ns[a])
    width = max(span // buckets, 1)
    bucket = (ns[a:b] - ns[a]) // width
    vals = values[a:b]
    if vals.dtype.kind not in "iuf":
        vals = np.zeros(len(vals))
    order = np.lexsort((vals, bucket))  # by bucket, then value
    sorted_bucket = bucket[order]
    boundary = sorted_bucket[1:] != sorted_bucket[:-1]
    first = np.concatenate(([True], boundary))
    last = np.concatenate((boundary, [True]))
    return np.sort(order[first | last]) + a
