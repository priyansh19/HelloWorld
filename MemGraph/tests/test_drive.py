"""Tests for the car's park/drift/turn state machine (Qt-free)."""

import math

from memgraph.drive_logic import Driver, DriveState, PARK_HYSTERESIS, PARK_YAW

LEFT, RIGHT = 0.0, 1000.0
CRUISE = 30.0
DT = 0.03
SPRITE_W = 40.0


def run(driver, st, ram, seconds):
    steps = int(seconds / DT)
    for _ in range(steps):
        driver.step(st, DT, ram, LEFT, RIGHT, CRUISE)
    return st


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


def test_high_ram_drifts_and_bounces():
    d = Driver(park_below=50)
    st = DriveState(x=500.0)
    xs = set()
    for _ in range(int(120 / DT)):
        d.step(st, DT, 80, LEFT, RIGHT, CRUISE)
        xs.add(round(st.x, -1))
    assert not st.parked
    assert min(xs) <= 10 and max(xs) >= 990  # touched both edges


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


def test_turn_sweeps_yaw_through_the_ring():
    d = Driver(park_below=50)
    st = DriveState(x=RIGHT - 1, yaw=0.0, facing=1)
    seen = set()
    for _ in range(int(3 / DT)):
        d.step(st, DT, 70, LEFT, RIGHT, CRUISE)
        seen.add(round(st.yaw / 15))         # bucketised headings
    assert st.facing == -1
    assert st.yaw == 180.0                   # ends facing left
    assert len(seen) > 4                     # passed through mid angles


def test_donut_spins_a_full_extra_circle_above_80():
    d = Driver(park_below=50, donut_above=80)
    normal = DriveState(x=RIGHT - 1, yaw=0.0, facing=1)
    donut = DriveState(x=RIGHT - 1, yaw=0.0, facing=1)
    total_n = total_d = 0.0
    for _ in range(int(4 / DT)):
        py_n, py_d = normal.yaw, donut.yaw
        d.step(normal, DT, 70, LEFT, RIGHT, CRUISE)
        d.step(donut, DT, 92, LEFT, RIGHT, CRUISE)
        total_n += (normal.yaw - py_n) % 360.0
        total_d += (donut.yaw - py_d) % 360.0
    assert donut.yaw == 180.0                # still ends facing the other way
    assert total_d >= total_n + 300.0        # ...after ~a full extra circle


def test_speed_doubles_at_the_donut_threshold():
    # Speed now ramps up (see test_speed_ramps_up_smoothly), so give both
    # states time to reach their cruising speed before comparing.
    d = Driver(park_below=50, donut_above=80)
    calm = DriveState(x=500.0)
    hot = DriveState(x=500.0)
    for _ in range(60):
        d.step(calm, DT, 55, LEFT, RIGHT, CRUISE)
        d.step(hot, DT, 85, LEFT, RIGHT, CRUISE)
    assert hot.speed >= 2.0 * CRUISE         # "almost twice normal"
    assert calm.speed < 1.2 * CRUISE


def test_speed_ramps_up_smoothly_not_instantly():
    # The whole point of the accel/brake model: a single tiny tick must NOT
    # jump straight to the target cruise speed.
    d = Driver(park_below=50, donut_above=80)
    st = DriveState(x=500.0)
    d.step(st, DT, 90, LEFT, RIGHT, CRUISE)
    assert 0.0 < st.speed < 2.0 * CRUISE * 0.5


def test_car_brakes_smoothly_before_the_edge():
    # As the car nears an edge its speed should fall well before it actually
    # arrives — a real brake, not an instant stop at the boundary.
    d = Driver(park_below=50, donut_above=200)  # keep this a plain turn
    st = DriveState(x=RIGHT - 40, yaw=0.0, facing=1)
    for _ in range(30):
        d.step(st, DT, 70, LEFT, RIGHT, CRUISE)
        if st.x >= RIGHT - 5 and not st.turning:
            break
    assert st.speed < CRUISE * 1.5 * 0.9     # braked down, not at full tilt


def test_parks_facing_front():
    d = Driver(park_below=50)
    st = DriveState(x=200.0)
    run(d, st, ram=30, seconds=30)
    assert st.parked
    assert math.isclose(st.yaw % 360.0, PARK_YAW, abs_tol=1.0)


def test_donut_pivots_around_a_fixed_nose_point():
    # Pure pivot-formula check, given room to spare: start the spin directly
    # (rather than via an edge bounce, which by construction leaves zero
    # clearance on one side — see test_donut_never_pushes_the_widget_off_screen
    # for that safety-critical case) and confirm the nose stays essentially
    # fixed while the widget position swings to hold it there.
    d = Driver(park_below=50, donut_above=80)
    wide_right = RIGHT + 500.0    # plenty of clearance either side
    st = DriveState(x=RIGHT - 1, yaw=0.0, facing=1)
    d._begin_turn_if_needed(st, donut=True, sprite_w_px=SPRITE_W)
    anchors = []
    for _ in range(int(2 / DT)):
        d.step(st, DT, 92, LEFT, wide_right, CRUISE, sprite_w_px=SPRITE_W)
        if not st.turning:
            break
        nose_frac = 0.5 + 0.48 * math.cos(math.radians(st.yaw))
        anchors.append(st.x + nose_frac * SPRITE_W)
    assert len(anchors) > 5
    assert max(anchors) - min(anchors) < 2.0   # nose held essentially still


def test_donut_never_pushes_the_widget_off_screen():
    # A donut always starts flush against the edge that triggered it (the
    # normal, only way it triggers in the app), so for part of the spin the
    # ideal nose-locked position would sit past that edge. Staying on-screen
    # must win over a perfectly pinned nose in that squeeze.
    d = Driver(park_below=50, donut_above=80)
    st = DriveState(x=RIGHT, yaw=0.0, facing=1)
    xs = []
    for _ in range(int(2 / DT)):
        d.step(st, DT, 92, LEFT, RIGHT, CRUISE, sprite_w_px=SPRITE_W)
        xs.append(st.x)
        if not st.turning:
            break
    assert xs, "the donut never actually ran"
    assert all(LEFT <= x <= RIGHT for x in xs)     # never off-screen


def test_turning_keeps_wheels_churning():
    d = Driver(park_below=50)
    st = DriveState(x=RIGHT, yaw=0.0, facing=1)
    d.step(st, DT, 80, LEFT, RIGHT, CRUISE)  # triggers the turn
    before = st.spin
    d.step(st, DT, 80, LEFT, RIGHT, CRUISE)
    assert st.turning or st.yaw != 0.0
    assert st.spin > before                  # burnout through the slide


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
