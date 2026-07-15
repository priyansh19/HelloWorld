from memgraph.buddy_logic import (
    GALLOP_FRAMES,
    PALETTE,
    SPRITE_H,
    SPRITE_W,
    WALK_FRAMES,
    apply_overlays,
    frames_for_gait,
    mood_for,
)


def _assert_frame_valid(rows):
    assert len(rows) == SPRITE_H
    for row in rows:
        assert len(row) == SPRITE_W
        for ch in row:
            assert ch == "." or ch in PALETTE


def test_all_base_frames_valid():
    for frame in WALK_FRAMES + GALLOP_FRAMES:
        _assert_frame_valid(frame)


def test_overlays_keep_frame_valid():
    for frame in WALK_FRAMES:
        for pack in ("normal", "full"):
            for shades in (False, True):
                for blink in (False, True):
                    _assert_frame_valid(apply_overlays(
                        frame, pack=pack, shades=shades, blink=blink))


def test_overlays_do_not_mutate_original():
    frame = WALK_FRAMES[0]
    before = list(frame)
    apply_overlays(frame, pack="full", shades=True)
    assert frame == before


def test_shades_and_pack_pixels_present():
    rows = apply_overlays(WALK_FRAMES[0], pack="full", shades=True)
    joined = "\n".join(rows)
    assert "S" in joined          # sunglasses
    assert "P" in joined          # pack
    assert "p" in joined          # full-pack highlight


def test_frames_for_gait():
    assert frames_for_gait("gallop") is GALLOP_FRAMES
    assert frames_for_gait("walk") is WALK_FRAMES
    assert frames_for_gait("idle") is WALK_FRAMES


def test_mood_gaits():
    assert mood_for(5, 30, 70, 88, False).gait == "idle"
    assert mood_for(30, 30, 70, 88, False).gait == "walk"
    assert mood_for(80, 30, 70, 88, False).gait == "gallop"


def test_mood_panic_forces_gallop():
    m = mood_for(3, 95, 70, 88, False)
    assert m.panic is True
    assert m.gait == "gallop"
    assert m.wander_ok is False


def test_mood_pack_follows_amber():
    assert mood_for(10, 50, 70, 88, False).pack == "normal"
    assert mood_for(10, 75, 70, 88, False).pack == "full"


def test_mood_shades_follow_model():
    assert mood_for(10, 10, 70, 88, True).shades is True
    assert mood_for(10, 10, 70, 88, False).shades is False


def test_frame_interval_speeds_up_with_cpu():
    slow = mood_for(20, 10, 70, 88, False).frame_ms
    fast = mood_for(95, 10, 70, 88, False).frame_ms
    assert fast < slow
    assert fast >= 60  # never below the floor


def test_wander_only_when_relaxed():
    assert mood_for(5, 10, 70, 88, False).wander_ok is True
    assert mood_for(90, 10, 70, 88, False).wander_ok is False
