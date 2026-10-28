import numpy as np

from canviewer.decimate import MAX_POINTS, select


def make(n=200_000):
    ns = (np.arange(n, dtype="int64") * 1_000_000)  # 1 kHz
    vals = np.sin(np.arange(n) / 50.0)
    return ns, vals


def test_small_windows_are_returned_whole():
    ns, vals = make(100)
    assert len(select(ns, vals, None, None)) == 100


def test_large_windows_are_capped_and_sorted():
    ns, vals = make()
    idx = select(ns, vals, None, None)
    assert len(idx) <= MAX_POINTS + 2 and np.all(np.diff(idx) > 0)


def test_spikes_survive():
    ns, vals = make()
    vals[123_457] = 99.0
    assert 123_457 in select(ns, vals, None, None)


def test_gaps_survive():
    ns, vals = make()
    keep = np.r_[0:50_000, 150_000:200_000]  # 100 s silence
    ns, vals = ns[keep], vals[keep]
    t = ns[select(ns, vals, None, None)]
    assert np.diff(t).max() >= 99_000_000_000


def test_zoom_restores_detail():
    ns, vals = make()
    lo, hi = ns[1000], ns[1999]
    idx = select(ns, vals, lo, hi)
    assert len(idx) == 1000 and idx[0] == 1000


def test_non_numeric_values_do_not_crash():
    ns, _ = make()
    vals = np.array(["a"] * len(ns), dtype=object)
    assert len(select(ns, vals, None, None)) <= MAX_POINTS + 2
