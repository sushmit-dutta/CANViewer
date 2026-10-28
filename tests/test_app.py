from canviewer.app import create_app
from canviewer.export import build_export_html
from canviewer import frames as fr


def test_app_builds_and_registers_callbacks(log_data):
    app = create_app(log_data)
    assert app.layout is not None
    assert len(app.callback_map) >= 8


def test_export_contains_each_plotted_frame_and_cursor_table(log_data):
    f = fr.new_frame()
    frames = fr.add_signals([f, fr.new_frame()], f["id"], ["Volt", "Temp"])
    cursors = [{"id": "c1", "x": "2026-11-21 06:13:20", "color": "#f6c90e"}]
    html = build_export_html(frames, log_data, cursors, "dark")
    assert html.count("plotly-graph-div") == 1  # empty frame skipped
    assert "Volt" in html and "<table>" in html
