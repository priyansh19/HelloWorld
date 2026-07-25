from memgraph import car_logic as C


def _assert_frame_valid(rows):
    assert len(rows) == C.SPRITE_H
    for row in rows:
        assert len(row) == C.SPRITE_W
        for ch in row:
            assert ch == "." or ch in C.PALETTE


def test_all_frames_valid():
    for frame in C.WALK_FRAMES + C.GALLOP_FRAMES:
        _assert_frame_valid(frame)


def test_frames_for_gait_always_defined():
    for gait in ("idle", "walk", "gallop"):
        _assert_frame_valid(C.frames_for_gait(gait)[0])


def test_overlays_are_noop_but_valid():
    rows = C.WALK_FRAMES[0]
    out = C.apply_overlays(rows, shades=True, blink=True)
    assert out == list(rows)
    _assert_frame_valid(out)


def test_wheels_spin_between_frames():
    # The rotating spokes must actually change the sprite frame to frame.
    assert C.WALK_FRAMES[0] != C.WALK_FRAMES[2]


def test_car_never_reddens_under_ram_tint():
    # Smoke conveys RAM stress for the car, so every glyph is tint-exempt.
    for frame in C.WALK_FRAMES:
        for row in frame:
            for ch in row:
                if ch != ".":
                    assert ch in C.TINT_EXEMPT


def test_exhaust_is_inside_the_sprite():
    ex, ey = C.EXHAUST
    assert 0 <= ex < C.SPRITE_W
    assert 0 <= ey < C.SPRITE_H
