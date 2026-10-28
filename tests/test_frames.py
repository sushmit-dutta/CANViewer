from canviewer import frames as fr


def fresh(*ids):
    return [{**fr.new_frame(), "id": i} for i in ids]


def sync(prev_frames, new_frames):
    prev = None if prev_frames is None else [fr.fingerprint(f) for f in prev_frames]
    return fr.diff(prev, new_frames)


def test_add_signals_assigns_distinct_colours_and_dedupes():
    frames = fr.add_signals(fresh("a"), "a", ["x", "y", "x"])
    assert frames[0]["signals"] == ["x", "y"]
    assert len(set(frames[0]["colors"].values())) == 2


def test_colours_stay_put_when_a_signal_is_removed():
    frames = fr.add_signals(fresh("a"), "a", ["x", "y", "z"])
    before = dict(frames[0]["colors"])
    frames = fr.remove_signal(frames, "a", "y")
    assert frames[0]["colors"] == {"x": before["x"], "z": before["z"]}


def test_remove_signal_also_unhides_it():
    frames = fr.toggle_hidden(fr.add_signals(fresh("a"), "a", ["x"]), "a", "x")
    assert frames[0]["hidden"] == ["x"]
    assert fr.remove_signal(frames, "a", "x")[0]["hidden"] == []


def test_toggle_hidden_round_trips():
    frames = fr.add_signals(fresh("a"), "a", ["x"])
    twice = fr.toggle_hidden(fr.toggle_hidden(frames, "a", "x"), "a", "x")
    assert twice[0]["hidden"] == []


def test_move_frame_moves_rather_than_swaps():
    frames = fresh("a", "b", "c")
    # Dragging down lands after the target, up lands before it; nothing swaps.
    assert [f["id"] for f in fr.move_frame(frames, "a", "c")] == ["b", "c", "a"]
    assert [f["id"] for f in fr.move_frame(frames, "c", "a")] == ["c", "a", "b"]
    assert fr.move_frame(frames, "a", "zzz") == frames


def test_diff_first_render_is_full():
    assert sync(None, fresh("a")) is None


def test_diff_nothing_changed():
    f = fresh("a", "b")
    assert sync(f, f) == []


def test_diff_append_touches_only_the_new_card():
    old = fresh("a", "b")
    assert sync(old, old + fresh("c")) == [("append",)]


def test_diff_delete_touches_only_that_card():
    old = fresh("a", "b", "c")
    assert sync(old, [old[0], old[2]]) == [("delete", 1)]


def test_diff_signal_drop_replaces_one_card():
    old = fresh("a", "b")
    new = fr.add_signals(old, "b", ["x"])
    assert sync(old, new) == [("replace", 1)]


def test_diff_reorder_needs_full_rebuild():
    old = fresh("a", "b")
    assert sync(old, [old[1], old[0]]) is None


def test_fingerprint_survives_json_round_trip():
    import json

    f = fr.add_signals(fresh("a"), "a", ["x"])[0]
    assert json.loads(json.dumps(fr.fingerprint(f))) == fr.fingerprint(f)
