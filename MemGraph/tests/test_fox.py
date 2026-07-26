"""Tests for the fox's RAM-band behaviour state machine (Qt-free)."""

from memgraph.fox_logic import (
    FoxDriver,
    FoxState,
    RUN_CLIP,
    SLEEP_CLIP,
    WALK_CLIP,
)

LEFT, RIGHT = 0.0, 1000.0
WALK = 40.0
DT = 0.03
SW, SH = 60.0, 36.0


def run(d, st, ram, seconds):
    for _ in range(int(seconds / DT)):
        d.step(st, DT, ram, LEFT, RIGHT, WALK, SW, SH)
    return st


def test_sleeps_in_the_left_corner_when_calm():
    d = FoxDriver(sleep_below=75, run_at=90, frenzy_at=95)
    st = FoxState(x=600.0)
    run(d, st, ram=40, seconds=60)
    assert st.state == "sleep"
    assert st.x == LEFT
    assert st.asleep
    assert st.clip == SLEEP_CLIP
    assert st.speed == 0.0
    assert st.y_off == 0.0


def test_roams_between_75_and_90():
    d = FoxDriver(sleep_below=75, run_at=90, frenzy_at=95)
    st = FoxState(x=500.0)
    xs = set()
    for _ in range(int(120 / DT)):
        d.step(st, DT, 82, LEFT, RIGHT, WALK, SW, SH)
        xs.add(round(st.x, -1))
    assert st.state == "roam"
    assert not st.asleep
    assert st.clip == WALK_CLIP
    assert min(xs) <= 10 and max(xs) >= 990    # roams the whole taskbar


def test_runs_between_90_and_95():
    d = FoxDriver(sleep_below=75, run_at=90, frenzy_at=95)
    walk = FoxState(x=500.0)
    run_st = FoxState(x=500.0)
    for _ in range(40):
        d.step(walk, DT, 82, LEFT, RIGHT, WALK, SW, SH)
        d.step(run_st, DT, 92, LEFT, RIGHT, WALK, SW, SH)
    assert run_st.state == "run"
    assert run_st.clip == RUN_CLIP
    assert run_st.speed > walk.speed * 1.5     # noticeably faster


def test_frenzy_jumps_off_the_walls_above_95():
    d = FoxDriver(sleep_below=75, run_at=90, frenzy_at=95)
    st = FoxState(x=RIGHT - 2, facing=1)
    hopped = False
    for _ in range(int(30 / DT)):
        d.step(st, DT, 97, LEFT, RIGHT, WALK, SW, SH)
        if st.y_off > 0.5:
            hopped = True
    assert st.state == "frenzy"
    assert hopped, "frenzy never jumped off a wall"
    assert st.speed > WALK * 2.5               # very fast


def test_jumps_always_return_to_the_taskbar():
    d = FoxDriver(sleep_below=75, run_at=90, frenzy_at=95)
    st = FoxState(x=RIGHT - 2, facing=1)
    max_off = 0.0
    for _ in range(int(30 / DT)):
        d.step(st, DT, 98, LEFT, RIGHT, WALK, SW, SH)
        max_off = max(max_off, st.y_off)
        assert st.y_off >= 0.0
    # never climbs off the taskbar strip (bounded to <1 sprite height)
    assert 0.0 < max_off < SH
    # a full crossing later, it has landed again at least once
    landings = 0
    for _ in range(int(20 / DT)):
        d.step(st, DT, 98, LEFT, RIGHT, WALK, SW, SH)
        if st.y_off == 0.0:
            landings += 1
    assert landings > 0


def test_hysteresis_no_flicker_at_the_sleep_edge():
    d = FoxDriver(sleep_below=75, run_at=90, frenzy_at=95)
    st = FoxState(x=500.0)
    run(d, st, ram=82, seconds=30)
    assert st.state == "roam"
    # dipping to exactly 75 must NOT immediately flip to sleep (needs -hyst)
    run(d, st, ram=74.5, seconds=3)
    assert st.state == "roam"
    run(d, st, ram=71, seconds=3)
    assert st.state == "sleep"


def test_walks_to_the_corner_before_sleeping():
    d = FoxDriver(sleep_below=75, run_at=90, frenzy_at=95)
    st = FoxState(x=800.0)
    # first steps at low RAM: heading to the corner, walking, not yet asleep
    d.step(st, DT, 30, LEFT, RIGHT, WALK, SW, SH)
    assert st.state == "sleep"
    assert not st.asleep          # still trotting over
    assert st.clip == WALK_CLIP
    assert st.x < 800.0           # moved toward the corner
