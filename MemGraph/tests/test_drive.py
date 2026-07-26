"""Tests for the car's park/drift/cone-loop state machine (Qt-free)."""

import math

from memgraph.drive_logic import (
    Driver,
    DriveState,
    PARK_HYSTERESIS,
    PARK_YAW,
    cone_centers,
    loop_radius,
)

LEFT, RIGHT = 0.0, 1000.0
CRUISE = 30.0
DT = 0.03
SPRITE_W, SPRITE_H = 40.0, 16.0


def run(driver, st, ram, seconds, sprite=False):
    kw = dict(sprite_w_px=SPRITE_W, sprite_h_px=SPRITE_H) if sprite else {}
    for _ in range(int(seconds / DT)):
        driver.step(st, DT, ram, LEFT, RIGHT, CRUISE, **kw)
    return st


# --------------------------------------------------------------------- #
# Parking
# --------------------------------------------------------------------- #
def test_low_ram_parks_at_nearest_corner():
    d = Driver(park_below=50)
    st = DriveState(x=200.0)
    run(d, st, ram=30, seconds=30)
    assert st.parked
    assert st.x == LEFT                      # 200 is nearer the left corner
    assert st.speed == 0.0                   # wheels stopped


def test_parks_on_the_right_when_nearer():
    d = Driver(park_below=50)
    st = DriveState(x=900.0)
    run(d, st, ram=30, seconds=30)
    assert st.parked and st.x == RIGHT


def test_parks_facing_front():
    d = Driver(park_below=50)
    st = DriveState(x=200.0)
    run(d, st, ram=30, seconds=30)
    assert st.parked
    assert math.isclose(st.yaw % 360.0, PARK_YAW, abs_tol=1.0)


def test_hysteresis_prevents_flapping():
    d = Driver(park_below=50)
    st = DriveState(x=100.0)
    run(d, st, ram=30, seconds=30)
    assert st.parked
    # hovering just above the line must NOT unpark (needs +hysteresis)
    run(d, st, ram=50 + PARK_HYSTERESIS - 0.5, seconds=5)
    assert st.parked
    run(d, st, ram=50 + PARK_HYSTERESIS + 1.0, seconds=5)
    assert not st.parked


def test_unpark_drives_back_into_the_screen():
    d = Driver(park_below=50)
    st = DriveState(x=100.0)
    run(d, st, ram=30, seconds=30)
    assert st.parked and st.x == LEFT
    run(d, st, ram=90, seconds=10)
    assert not st.parked and st.x > LEFT + 50


# --------------------------------------------------------------------- #
# Driving feel
# --------------------------------------------------------------------- #
def test_speed_ramps_up_smoothly_not_instantly():
    d = Driver(park_below=50, donut_above=80)
    st = DriveState(x=500.0)
    d.step(st, DT, 90, LEFT, RIGHT, CRUISE)
    assert 0.0 < st.speed < 2.0 * CRUISE * 0.5


def test_speed_doubles_at_the_donut_threshold():
    d = Driver(park_below=50, donut_above=80)
    calm = DriveState(x=500.0)
    hot = DriveState(x=500.0)
    for _ in range(60):
        d.step(calm, DT, 55, LEFT, RIGHT, CRUISE)
        d.step(hot, DT, 85, LEFT, RIGHT, CRUISE)
    assert hot.speed >= 2.0 * CRUISE         # "almost twice normal"
    assert calm.speed < 1.2 * CRUISE


def test_wheels_spin_in_proportion_to_speed():
    d = Driver(park_below=50)
    slow, fast = DriveState(x=500.0), DriveState(x=500.0)
    for _ in range(100):
        d.step(slow, DT, 55, LEFT, RIGHT, CRUISE)
        d.step(fast, DT, 95, LEFT, RIGHT, CRUISE)
    assert fast.spin > slow.spin * 1.3


def test_wheels_stop_only_when_parked():
    d = Driver(park_below=50)
    st = DriveState(x=100.0)
    run(d, st, ram=20, seconds=30)
    parked_spin = st.spin
    run(d, st, ram=20, seconds=5)
    assert st.spin == parked_spin            # no rolling while parked


# --------------------------------------------------------------------- #
# Cone loops
# --------------------------------------------------------------------- #
def test_cone_centers_sit_inside_the_screen():
    cx_l, cx_r = cone_centers(LEFT, RIGHT, SPRITE_W, SPRITE_W)
    assert LEFT < cx_l < cx_r < RIGHT + SPRITE_W


def test_drifts_around_the_cone_and_comes_back():
    d = Driver(park_below=50, donut_above=200)
    st = DriveState(x=500.0, facing=1)
    lifted = False
    looped = False
    for _ in range(int(60 / DT)):
        d.step(st, DT, 70, LEFT, RIGHT, CRUISE,
               sprite_w_px=SPRITE_W, sprite_h_px=SPRITE_H)
        if st.looping:
            looped = True
        if st.y_off > 1.0:
            lifted = True
        if looped and not st.looping:
            break
    assert looped, "the car never entered a cone loop"
    assert lifted, "the loop never lifted the car over the cone"
    assert st.facing == -1                   # exits heading back to the middle
    assert st.y_off == 0.0                   # back down on the taskbar
    assert math.isclose(st.yaw % 360.0, 180.0, abs_tol=1.0)


def test_loop_stays_on_screen():
    d = Driver(park_below=50, donut_above=80)
    st = DriveState(x=500.0, facing=1)
    for _ in range(int(60 / DT)):
        d.step(st, DT, 92, LEFT, RIGHT, CRUISE,
               sprite_w_px=SPRITE_W, sprite_h_px=SPRITE_H)
        assert LEFT - 0.01 <= st.x <= RIGHT + 0.01
        assert st.y_off >= 0.0


def test_loop_carries_drift_momentum():
    # A loop must never crawl: its pace is at least the momentum floor even
    # if the car entered slowly.
    d = Driver(park_below=50, donut_above=200)
    st = DriveState(x=RIGHT - 2 * loop_radius(SPRITE_W) - 1, facing=1,
                    speed=1.0)
    for _ in range(int(5 / DT)):
        d.step(st, DT, 70, LEFT, RIGHT, CRUISE,
               sprite_w_px=SPRITE_W, sprite_h_px=SPRITE_H)
        if st.looping:
            assert st._loop_speed >= 0.7 * CRUISE
            return
    raise AssertionError("never looped")


def test_hot_loop_adds_a_full_corkscrew():
    def total_yaw(ram):
        d = Driver(park_below=50, donut_above=80)
        st = DriveState(x=500.0, facing=1)
        total = 0.0
        prev = st.yaw
        looped = False
        for _ in range(int(60 / DT)):
            d.step(st, DT, ram, LEFT, RIGHT, CRUISE,
                   sprite_w_px=SPRITE_W, sprite_h_px=SPRITE_H)
            if st.looping:
                looped = True
                delta = abs((st.yaw - prev + 180.0) % 360.0 - 180.0)
                total += delta
            if looped and not st.looping:
                break
            prev = st.yaw
        return total
    assert total_yaw(92) >= total_yaw(70) + 300.0


def test_wheels_churn_through_the_loop():
    d = Driver(park_below=50, donut_above=200)
    st = DriveState(x=500.0, facing=1)
    for _ in range(int(60 / DT)):
        before = st.spin
        d.step(st, DT, 70, LEFT, RIGHT, CRUISE,
               sprite_w_px=SPRITE_W, sprite_h_px=SPRITE_H)
        if st.looping:
            assert st.spin > before          # burnout through the slide
            return
    raise AssertionError("never looped")
