import numpy as np
import pandas as pd

from canviewer.data import convert_to_mf4, load_log, to_epoch_ns
from conftest import N_STEPS, PACK_GAP, T0


def test_absolute_timestamps_are_not_shifted_by_header_start_time():
    start = pd.Timestamp("2000-01-01", tz="UTC")
    ns = to_epoch_ns(np.array([T0, T0 + 1]), start)
    assert ns[0] == int(T0 * 1e9)


def test_relative_timestamps_use_header_start_time():
    start = pd.Timestamp("2026-01-01", tz="UTC")
    ns = to_epoch_ns(np.array([0.0, 2.0]), start)
    assert ns[1] - ns[0] == 2_000_000_000
    assert ns[0] == int(start.timestamp() * 1e9)


def test_catalog_has_dbc_metadata(log_data):
    volt = log_data.catalog["Volt"]
    assert (volt.message, volt.unit, volt.comment, volt.senders) == ("Pack", "V", "pack voltage", ("BMS",))
    assert volt.message_id == 256
    assert log_data.catalog["State"].choices == {0: "Idle", 1: "Run"}
    assert log_data.messages == {"Pack": ["State", "Volt"], "Therm": ["Temp"]}


def test_series_are_the_signals_own_samples_with_gaps_intact(log_data):
    volt = log_data.series("Volt")
    assert volt.ns.size == N_STEPS - len(PACK_GAP)  # nothing interpolated in
    gaps = np.diff(volt.ns) / 1e9
    assert gaps.max() == pytest_approx(2.9)  # the 2.8 s silence is still a gap
    assert volt.ns[0] == int(T0 * 1e9)
    assert log_data.series("Temp").ns.size == 5


def test_physical_values_not_raw(log_data):
    assert log_data.series("Volt").values[0] == pytest_approx(400.0)


def test_local_time_round_trip(log_data):
    ns = log_data.series("Volt").ns[:3]
    text = str(log_data.local_times(ns)[1])
    assert log_data.local_to_ns(text) == ns[1]


def test_unknown_signal_is_none(log_data):
    assert log_data.series("Nope") is None


def test_asc_is_converted_into_cache_dir_and_reused(asc_path, tmp_path):
    first = convert_to_mf4(asc_path, tmp_path)
    assert first.parent == tmp_path and first.suffix == ".mf4"
    mtime = first.stat().st_mtime_ns
    assert convert_to_mf4(asc_path, tmp_path) == first
    assert first.stat().st_mtime_ns == mtime


def test_mf4_used_in_place(mf4_path, tmp_path):
    assert convert_to_mf4(mf4_path, tmp_path) == mf4_path.resolve()
    assert not list(tmp_path.iterdir())


def test_missing_dbc_is_reported(mf4_path, tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        load_log(str(mf4_path), str(tmp_path / "missing.dbc"), cache_dir=tmp_path)


def pytest_approx(x):
    import pytest

    return pytest.approx(x, abs=1e-3)
