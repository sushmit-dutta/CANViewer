from canviewer import frames as fr
from canviewer.cursors import add_cursor, CURSOR_COLORS, readings_at
from canviewer.figures import frame_figure
from conftest import N_STEPS, PACK_GAP, T0


def _frame(sigs):
    f = fr.new_frame()
    return fr.add_signals([f], f["id"], sigs)[0]


def test_every_signal_is_discrete_markers_at_its_own_samples(log_data):
    fig = frame_figure(_frame(["Volt", "Temp"]), log_data, "dark", [])
    assert [t.mode for t in fig.data] == ["markers", "markers"]
    assert len(fig.data[0].x) == N_STEPS - len(PACK_GAP)  # gap not filled
    assert len(fig.data[1].x) == 5  # Temp is not stretched to Volt's timebase


def test_empty_frame_is_a_placeholder(log_data):
    fig = frame_figure(_frame([]), log_data, "dark", [])
    assert len(fig.data) == 0 and fig.layout.annotations


def test_hidden_signal_trace_is_not_visible(log_data):
    f = _frame(["Volt", "Temp"])
    f["hidden"] = ["Volt"]
    fig = frame_figure(f, log_data, "dark", [])
    assert [t.visible for t in fig.data] == [False, True]


def test_enum_hover_uses_labels(log_data):
    fig = frame_figure(_frame(["State"]), log_data, "dark", [])
    assert set(fig.data[0].customdata) == {"Idle", "Run"}


def test_zoom_and_cursors_are_applied(log_data):
    cursors = add_cursor([], "2026-11-21 06:13:20")
    fig = frame_figure(_frame(["Volt"]), log_data, "light", cursors, ["2026-11-21", "2026-11-22"])
    assert list(fig.layout.xaxis.range) == ["2026-11-21", "2026-11-22"]
    assert len(fig.layout.shapes) == 1


def test_light_theme_changes_background(log_data):
    dark = frame_figure(_frame(["Volt"]), log_data, "dark", [])
    light = frame_figure(_frame(["Volt"]), log_data, "light", [])
    assert dark.layout.paper_bgcolor != light.layout.paper_bgcolor


def test_cursor_reads_last_sample_at_or_before(log_data):
    f = _frame(["Volt", "State"])
    inside = int((T0 + 0.15) * 1e9)  # between samples 1 (0.1) and 2 (missing)
    rows = {r.signal: r.text for r in readings_at(f, log_data, inside)}
    assert rows["Volt"].startswith("400.5")  # sample at +0.1 s, not +0.0 or +0.2
    assert rows["State"].startswith("Run")  # i=1 -> State 1


def test_cursor_inside_a_gap_flags_stale_value(log_data):
    f = _frame(["Volt"])
    rows = readings_at(f, log_data, int((T0 + 2.0) * 1e9))
    assert "s)" in rows[0].text  # age annotation, value not silently trusted


def test_cursor_before_first_sample_shows_dash(log_data):
    rows = readings_at(_frame(["Volt"]), log_data, int((T0 - 5) * 1e9))
    assert rows[0].text == "—"


def test_cursor_colours_never_repeat_and_oldest_is_evicted():
    cursors = []
    for i in range(len(CURSOR_COLORS) + 2):
        cursors = add_cursor(cursors, f"x{i}")
        colors = [c["color"] for c in cursors]
        assert len(colors) == len(set(colors))
    assert len(cursors) == len(CURSOR_COLORS)
    assert cursors[0]["x"] == "x2"
