"""Qt-free driving logic for the Mustang buddy.

The widget feeds this a time step, the live RAM %, and the drivable span; it
answers where the car is (x plus a lift off the taskbar), which way it points
(continuous yaw for the baked 3D frame ring) and how fast the wheels are
rolling. Keeping it pure makes the park/drift/loop behaviour unit-testable
without a display.

Behaviour spec:

* Speed and yaw rate are both **eased**, not snapped — the car accelerates up
  to its target speed and brakes like an actual driver.
* RAM below ``park_below`` → the car drives to the nearest screen corner,
  braking smoothly into the stop, and pivots to face front (the model's
  head-on frame) with wheels still (a small hysteresis band stops it
  flapping when RAM hovers on the line).
* RAM above the line → it drifts back and forth along the taskbar; cruise
  speed climbs with RAM (roughly doubling past ``donut_above``).
* Near each end of the screen stands a **traffic cone**. Instead of spinning
  in place, the car *drifts around the cone* in the ground plane — it never
  leaves the road. Viewed from the side, it swings past the cone on the
  outside, tucks in BEHIND it (the cone occludes the car, and the car sits a
  few pixels higher — the far lane of a shallow perspective ground), and
  comes back out heading the other way, yaw sweeping through the 3D ring the
  whole way round.
* Past ``donut_above`` the loop is a full extra orbit — the car circles the
  cone completely (front, outside, behind) before peeling off.
* Wheel spin rate is proportional to road speed at all times, churning
  through every loop like a proper burnout.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

TURN_RATE = 620.0        # deg/s for in-place pivots (parking / pulling out)
PARK_HYSTERESIS = 2.0    # RAM % band around park_below
ARRIVE_PX = 3.0          # close enough to the parking spot to stop
PARK_YAW = 90.0          # nose toward the viewer — the model's head-on frame

# Translational accel/brake (px/s^2). Braking is stronger than accelerating,
# like a real car, and both are finite so speed changes read as motion, not a
# teleport — this is what makes the drive feel driven rather than switched.
ACCEL_PX_S2 = 260.0
BRAKE_PX_S2 = 480.0

# Angular accel/brake (deg/s^2) for in-place pivots.
ANGULAR_ACCEL = 2600.0
ANGULAR_BRAKE = 3600.0

# Cone-loop geometry, as fractions of the sprite's on-screen size. The loop's
# horizontal radius controls how tight the circle around the cone is. The
# orbit stays in the ground plane: the far half of the circle renders a few
# pixels higher on screen (the "far lane" of a shallow perspective ground)
# and behind the cone — never airborne.
LOOP_R_FRAC = 0.55       # orbit radius vs sprite width
LOOP_DEPTH_FRAC = 0.22   # far-lane screen offset vs sprite height
CONE_H_FRAC = 0.44       # cone height vs sprite height

# The slowest the car will take a loop, as a fraction of its cruise target —
# a drift carries momentum; it never crawls around the cone.
LOOP_MIN_SPEED_FRAC = 0.75

# A drift is quicker than a cruise: entering an orbit the car eases up to a
# boosted pace (throttle punch), and winds back down over the last stretch so
# it exits at cruising speed — both ends stay continuous, no speed snaps.
ORBIT_SPEED_BOOST = 2.3
HOT_ORBIT_EXTRA = 1.25   # donut orbits carry even more pace
LOOP_ACCEL_PX_S2 = 520.0
ORBIT_WINDDOWN_DEG = 70.0


def loop_radius(sprite_w_px: float) -> float:
    """Horizontal radius of the cone loop for a car this wide on screen."""
    return max(8.0, LOOP_R_FRAC * sprite_w_px)


def cone_centers(left: float, right: float, widget_w_px: float,
                 sprite_w_px: float) -> tuple[float, float]:
    """Screen-x of the two cone centres (left cone, right cone).

    ``left``/``right`` are the widget-position extremes; each cone stands at
    the centre of its loop circle, i.e. one radius in from the extreme, at
    the car-centre offset.
    """
    r = loop_radius(sprite_w_px)
    half = widget_w_px / 2.0
    return (left + r + half, right - r + half)


def _ease(current: float, target: float, dt: float,
         accel: float, brake: float) -> float:
    """Move ``current`` toward ``target`` at up to ``accel``/``brake`` per
    second, whichever applies — the shared accelerate-or-brake primitive
    behind both road speed and turn rate."""
    diff = target - current
    if diff >= 0.0:
        return current + min(diff, accel * dt)
    return current + max(diff, -brake * dt)


def _ram_speed_mult(ram_pct: float, park_below: float,
                    donut_above: float) -> float:
    """Speed multiplier vs RAM: eases from 1x just past the park line up to
    ~1.5x approaching the donut threshold, then snaps to ~2x ("almost twice
    normal") once the machine is really burning."""
    if ram_pct >= donut_above:
        return 2.0 + 0.3 * min(1.0, (ram_pct - donut_above) / 20.0)
    span = max(1.0, donut_above - park_below)
    return 1.0 + 0.5 * max(0.0, ram_pct - park_below) / span


@dataclass
class DriveState:
    x: float = 0.0            # left edge of the widget, px
    y_off: float = 0.0        # lift above the taskbar, px (loops only)
    yaw: float = 0.0          # heading, deg; 0 faces right, 180 faces left
    spin: float = 0.0         # wheel phase in revolutions (fractional)
    facing: int = 1           # travel intent: +1 right, -1 left
    parked: bool = False
    turning: bool = False     # in-place pivot (parking / pulling out)
    looping: bool = False     # drifting around a cone
    behind: bool = False      # on the far side — the cone occludes the car
    speed: float = 0.0        # current road speed, px/s (eased, not target)
    park_side: int = 0        # -1 left corner, +1 right corner, 0 undecided
    # in-place pivot bookkeeping
    _turn_target: float = field(default=0.0, repr=False)
    _sweep_left: float = field(default=0.0, repr=False)
    _turn_dir: float = field(default=1.0, repr=False)
    _ang_speed: float = field(default=0.0, repr=False)
    # cone-loop bookkeeping (orbit angle in degrees; see _loop_step)
    _loop_side: int = field(default=1, repr=False)        # +1 right, -1 left
    _loop_theta: float = field(default=270.0, repr=False)
    _loop_end: float = field(default=450.0, repr=False)
    _loop_speed: float = field(default=0.0, repr=False)
    _loop_base_speed: float = field(default=0.0, repr=False)
    _loop_target_speed: float = field(default=0.0, repr=False)
    _depth_px: float = field(default=0.0, repr=False)


class Driver:
    """Advances a :class:`DriveState` through park/drift/loop behaviour."""

    def __init__(self, park_below: float = 50.0, donut_above: float = 80.0,
                 wheel_circumference_px: float = 46.0) -> None:
        self.park_below = float(park_below)
        self.donut_above = float(donut_above)
        self.wheel_circ = max(8.0, wheel_circumference_px)

    # -------------------------------------------------------------- #
    def step(self, st: DriveState, dt: float, ram_pct: float,
             left: float, right: float, cruise_px_s: float,
             sprite_w_px: float = 0.0, sprite_h_px: float = 0.0) -> DriveState:
        """One simulation step of ``dt`` seconds. Mutates and returns ``st``.

        ``sprite_w_px``/``sprite_h_px`` size the cone loops; without them the
        car falls back to a simple in-place turn at the extremes.
        """
        if right <= left:
            return st

        # ---- park / drift decision with hysteresis -------------------
        if st.parked:
            if ram_pct > self.park_below + PARK_HYSTERESIS:
                st.parked = False
                st.park_side = 0
                # pull away from the corner toward the open screen
                st.facing = 1 if st.x < (left + right) / 2 else -1
                self._begin_turn_if_needed(st)
        else:
            if ram_pct < self.park_below - PARK_HYSTERESIS and not st.looping:
                st.parked = True
                st.park_side = -1 if st.x < (left + right) / 2 else 1

        # ---- mid-loop: circle the cone -------------------------------
        if st.looping:
            self._loop_step(st, dt, left, right, sprite_w_px, sprite_h_px)
            return st

        # ---- easing back to the near lane after a loop ----------------
        if st.y_off > 0.0:
            fall = max(20.0, st._depth_px / 0.35)      # ~0.35 s to rejoin
            st.y_off = max(0.0, st.y_off - fall * dt)
            if st.y_off <= 0.5:
                st.y_off = 0.0
                st.behind = False

        # ---- in-place pivot (parking or pulling out) -----------------
        if st.turning:
            brake_rate = math.sqrt(max(0.0, 2.0 * ANGULAR_BRAKE * st._sweep_left))
            desired_rate = min(TURN_RATE, brake_rate)
            st._ang_speed = _ease(st._ang_speed, desired_rate, dt,
                                  ANGULAR_ACCEL, ANGULAR_BRAKE)
            d = st._ang_speed * dt * st._turn_dir
            st.yaw = (st.yaw + d) % 360.0
            st._sweep_left -= abs(d)
            if st._sweep_left <= 0.5:
                st.yaw = st._turn_target % 360.0
                st.turning = False
                st._ang_speed = 0.0
            return st

        # ---- parked: brake smoothly into the corner, face front, stop -
        if st.parked:
            target_x = left if st.park_side < 0 else right
            delta = target_x - st.x
            dist = abs(delta)
            if dist > ARRIVE_PX:
                want = 1 if delta > 0 else -1
                if want != st.facing:
                    st.facing = want
                    self._begin_turn_if_needed(st)
                    return st
                brake_v = math.sqrt(max(0.0, 2.0 * BRAKE_PX_S2 * dist))
                desired = min(cruise_px_s, brake_v)
                st.speed = _ease(st.speed, desired, dt, ACCEL_PX_S2, BRAKE_PX_S2)
                st.x += st.facing * st.speed * dt
                st.spin += st.speed * dt / self.wheel_circ
            else:
                st.x = target_x
                st.speed = 0.0            # wheels stop with the car
                if not math.isclose(st.yaw % 360.0, PARK_YAW, abs_tol=1.0):
                    self._begin_turn_if_needed(st, target=PARK_YAW)
            return st

        # ---- cruising: accelerate toward target, loop at each cone ----
        target_speed = cruise_px_s * _ram_speed_mult(ram_pct, self.park_below,
                                                      self.donut_above)
        st.speed = _ease(st.speed, target_speed, dt, ACCEL_PX_S2, BRAKE_PX_S2)
        st.x += st.facing * st.speed * dt
        st.spin += st.speed * dt / self.wheel_circ

        if sprite_w_px > 0:
            r = loop_radius(sprite_w_px)
            roomy = (right - left) >= 2.2 * r
            if st.facing > 0 and st.x >= right - r:
                if roomy:
                    self._begin_loop(st, side=1, ram_pct=ram_pct,
                                     cruise=target_speed,
                                     sprite_h_px=sprite_h_px)
                else:                            # tiny screen: pivot in place
                    st.x = min(st.x, right)
                    st.facing = -1
                    self._begin_turn_if_needed(st)
            elif st.facing < 0 and st.x <= left + r:
                if roomy:
                    self._begin_loop(st, side=-1, ram_pct=ram_pct,
                                     cruise=target_speed,
                                     sprite_h_px=sprite_h_px)
                else:
                    st.x = max(st.x, left)
                    st.facing = 1
                    self._begin_turn_if_needed(st)
        # safety clamp for tiny screens / missing sprite size
        if st.x <= left:
            st.x = left
            st.facing = 1
            self._begin_turn_if_needed(st)
        elif st.x >= right:
            st.x = right
            st.facing = -1
            self._begin_turn_if_needed(st)
        return st

    # -------------------------------------------------------------- #
    # Cone loops
    # -------------------------------------------------------------- #
    def _begin_loop(self, st: DriveState, side: int, ram_pct: float,
                    cruise: float, sprite_h_px: float) -> None:
        """Join the cone's orbit at its near-side point.

        The orbit is a ground-plane circle around the cone, parametrised by
        ``theta``: 270 is directly in FRONT of the cone (near lane — where a
        car cruising past naturally sits, heading unchanged), 0/360 is the
        outside extreme level with the cone, 90/450 directly BEHIND it. A
        turn-around is half an orbit (270 -> 450); past the donut threshold
        the car does a full extra circle first (270 -> 810).
        """
        st.looping = True
        st._loop_side = side
        st._loop_theta = 270.0
        hot = ram_pct >= self.donut_above
        st._loop_end = 270.0 + 180.0 + (360.0 if hot else 0.0)
        base = max(st.speed, LOOP_MIN_SPEED_FRAC * cruise)
        st._loop_base_speed = base
        st._loop_target_speed = base * ORBIT_SPEED_BOOST * \
            (HOT_ORBIT_EXTRA if hot else 1.0)
        st._loop_speed = max(st.speed, 0.9 * base)   # continuous with entry
        st._depth_px = LOOP_DEPTH_FRAC * max(1.0, sprite_h_px)

    def _loop_step(self, st: DriveState, dt: float, left: float, right: float,
                   sprite_w_px: float, sprite_h_px: float) -> None:
        r = loop_radius(sprite_w_px)
        # Throttle punch in, wind down out: ease toward the boosted drift pace
        # for most of the orbit, then back toward entry pace over the final
        # degrees so the exit hands cruising a speed it already has.
        remaining = st._loop_end - st._loop_theta
        target = (st._loop_target_speed if remaining > ORBIT_WINDDOWN_DEG
                  else st._loop_base_speed)
        st._loop_speed = _ease(st._loop_speed, target, dt,
                               LOOP_ACCEL_PX_S2, BRAKE_PX_S2)
        v = st._loop_speed
        st.speed = v
        st.spin += v * dt / self.wheel_circ      # wheels churn throughout

        # advance around the circle at the drift's road speed
        st._loop_theta += math.degrees(v * dt / r)
        done = st._loop_theta >= st._loop_end
        theta = min(st._loop_theta, st._loop_end)
        a = math.radians(theta)

        cone_wx = (right - r) if st._loop_side > 0 else (left + r)
        st.x = cone_wx + st._loop_side * r * math.cos(a)
        st.x = max(left, min(right, st.x))
        # ground-plane depth: the far half of the orbit sits a few pixels
        # higher on screen (far lane) and behind the cone — never airborne.
        z = math.sin(a)                          # -1 near .. +1 far
        y_target = st._depth_px * (z + 1.0) / 2.0
        if st.y_off > y_target:                  # residual from a prior loop
            fall = max(20.0, st._depth_px / 0.35)
            st.y_off = max(y_target, st.y_off - fall * dt)
        else:
            st.y_off = y_target
        st.behind = z > 0.0
        # heading = the orbit's tangent, mapped onto the baked yaw ring
        # (yaw 0 faces screen-right, yaw 90 faces away from the viewer)
        if st._loop_side > 0:
            st.yaw = (theta + 90.0) % 360.0
        else:
            st.yaw = (90.0 - theta) % 360.0

        if done:
            st.looping = False
            st.facing = -st._loop_side
            st.yaw = 0.0 if st.facing == 1 else 180.0
            # y_off/behind ease back to the near lane during cruising

    # -------------------------------------------------------------- #
    def _begin_turn_if_needed(self, st: DriveState,
                              target: float | None = None) -> None:
        """Start an in-place yaw pivot toward ``target`` (default: the heading
        that matches ``st.facing``), by the shortest rotation."""
        if target is None:
            target = 0.0 if st.facing == 1 else 180.0
        diff = ((target - st.yaw + 180.0) % 360.0) - 180.0
        if diff == -180.0:
            diff = 180.0
        sweep = abs(diff)
        if sweep < 1.0:
            return
        st._turn_target = target
        st._sweep_left = sweep
        st._turn_dir = 1.0 if diff >= 0 else -1.0
        st._ang_speed = 0.0
        st.turning = True

    # -------------------------------------------------------------- #
    @staticmethod
    def spin_phase(st: DriveState) -> float:
        """Wheel phase in [0, 1) for frame lookup."""
        return st.spin % 1.0
