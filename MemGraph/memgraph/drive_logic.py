"""Qt-free driving logic for the Mustang buddy.

The widget feeds this a time step, the live RAM %, and the drivable span; it
answers where the car is, which way it points (continuous yaw for the baked 3D
frame ring) and how fast the wheels are rolling. Keeping it pure makes the
park/drift/brake behaviour unit-testable without a display.

Behaviour spec:

* Speed and yaw rate are both **eased**, not snapped — the car accelerates up
  to its target speed and brakes into corners/edges like an actual driver,
  and a turn spins up then winds down instead of an instant constant rate.
* RAM below ``park_below`` → the car drives to the nearest screen corner,
  braking smoothly into the stop, and pivots to face front (the model's
  head-on frame) with wheels still (a small hysteresis band stops it
  flapping when RAM hovers on the line).
* RAM above the line → it drifts back and forth along the taskbar, braking
  toward each edge and accelerating away after the turn; cruise speed climbs
  with RAM.
* At each edge it *turns around*, wheels kept spinning through the slide like
  a real burnout turn.
* Past ``donut_above`` it throws in a full extra circle at each edge — a real
  donut — and the nose stays pinned to one screen point while the rear swings
  around it, rather than spinning about the car's own centre. Cruise speed
  also roughly doubles.
* Wheel spin rate is proportional to road speed at all times.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

TURN_RATE = 620.0        # deg/s the yaw sweeps at, once spun up
DONUT_RATE = 760.0       # deg/s during a donut — a drift spin is quicker
PARK_HYSTERESIS = 2.0    # RAM % band around park_below
ARRIVE_PX = 3.0          # close enough to the parking spot to stop
PARK_YAW = 90.0          # nose toward the viewer — the model's head-on frame

# Translational accel/brake (px/s^2). Braking is stronger than accelerating,
# like a real car, and both are finite so speed changes read as motion, not a
# teleport — this is what makes the drive feel driven rather than switched.
ACCEL_PX_S2 = 260.0
BRAKE_PX_S2 = 480.0

# Angular accel/brake (deg/s^2) for the yaw sweep — a turn spins up to its
# rate and winds down into the finish, instead of snapping to constant speed.
ANGULAR_ACCEL = 2600.0
ANGULAR_BRAKE = 3600.0

# How far the nose sits from the sprite's horizontal centre, as a fraction of
# sprite width, at yaw 0 (facing right). The baked camera frames the car about
# its own geometric centre, so the nose swings as cos(yaw) about that centre;
# 0.48 matches how close the nose sits to the frame edge in the bake.
_NOSE_AMPLITUDE = 0.48


def _nose_u(yaw_deg: float) -> float:
    """Nose position as a fraction of sprite width, 0=left edge, 1=right."""
    return 0.5 + _NOSE_AMPLITUDE * math.cos(math.radians(yaw_deg))


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
    yaw: float = 0.0          # heading, deg; 0 faces right, 180 faces left
    spin: float = 0.0         # wheel phase in revolutions (fractional)
    facing: int = 1           # travel intent: +1 right, -1 left
    parked: bool = False
    turning: bool = False
    speed: float = 0.0        # current road speed, px/s (eased, not target)
    park_side: int = 0        # -1 left corner, +1 right corner, 0 undecided
    _turn_target: float = field(default=0.0, repr=False)
    _sweep_left: float = field(default=0.0, repr=False)   # degrees still to turn
    _turn_rate: float = field(default=TURN_RATE, repr=False)  # target rate
    _turn_dir: float = field(default=1.0, repr=False)     # +1 CCW, -1 CW
    _ang_speed: float = field(default=0.0, repr=False)    # current yaw rate
    _is_donut: bool = field(default=False, repr=False)
    _pivot_anchor_x: float = field(default=0.0, repr=False)


class Driver:
    """Advances a :class:`DriveState` through park/drift/turn behaviour."""

    def __init__(self, park_below: float = 50.0, donut_above: float = 80.0,
                 wheel_circumference_px: float = 46.0) -> None:
        self.park_below = float(park_below)
        self.donut_above = float(donut_above)
        self.wheel_circ = max(8.0, wheel_circumference_px)

    # -------------------------------------------------------------- #
    def step(self, st: DriveState, dt: float, ram_pct: float,
             left: float, right: float, cruise_px_s: float,
             sprite_w_px: float = 0.0) -> DriveState:
        """One simulation step of ``dt`` seconds. Mutates and returns ``st``.

        ``sprite_w_px`` is the car's on-screen width; it is only needed to
        anchor the nose during a donut and can be omitted otherwise.
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
            if ram_pct < self.park_below - PARK_HYSTERESIS:
                st.parked = True
                st.park_side = -1 if st.x < (left + right) / 2 else 1

        # ---- turning: spin up to the turn rate, sweep yaw, wind down --
        # A donut is the same sweep plus a full extra 360 revolution, with
        # the nose pinned to a fixed screen point while the rest swings
        # about it.
        if st.turning:
            brake_rate = math.sqrt(max(0.0, 2.0 * ANGULAR_BRAKE * st._sweep_left))
            desired_rate = min(st._turn_rate, brake_rate)
            st._ang_speed = _ease(st._ang_speed, desired_rate, dt,
                                  ANGULAR_ACCEL, ANGULAR_BRAKE)
            d = st._ang_speed * dt * st._turn_dir
            st.yaw = (st.yaw + d) % 360.0
            st._sweep_left -= abs(d)
            if st._sweep_left <= 0.5:
                st.yaw = st._turn_target % 360.0
                st.turning = False
                st._ang_speed = 0.0
            if st._is_donut and sprite_w_px > 0:
                st.x = st._pivot_anchor_x - _nose_u(st.yaw) * sprite_w_px
            # burnout: wheels churn through the slide at the pre-turn rate
            st.spin += max(st.speed, cruise_px_s) * dt / self.wheel_circ
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

        # ---- drifting back and forth, braking into each edge ----------
        donut = ram_pct >= self.donut_above
        target_speed = cruise_px_s * _ram_speed_mult(ram_pct, self.park_below,
                                                      self.donut_above)
        dist = (right - st.x) if st.facing > 0 else (st.x - left)
        brake_v = math.sqrt(max(0.0, 2.0 * BRAKE_PX_S2 * max(0.0, dist)))
        desired = min(target_speed, brake_v)
        st.speed = _ease(st.speed, desired, dt, ACCEL_PX_S2, BRAKE_PX_S2)
        st.x += st.facing * st.speed * dt
        st.spin += st.speed * dt / self.wheel_circ
        if st.x <= left:
            st.x = left
            st.facing = 1
            self._begin_turn_if_needed(st, donut=donut, sprite_w_px=sprite_w_px)
        elif st.x >= right:
            st.x = right
            st.facing = -1
            self._begin_turn_if_needed(st, donut=donut, sprite_w_px=sprite_w_px)
        return st

    # -------------------------------------------------------------- #
    def _begin_turn_if_needed(self, st: DriveState, donut: bool = False,
                              target: float | None = None,
                              sprite_w_px: float = 0.0) -> None:
        """Start a yaw sweep toward ``target`` (default: the heading that
        matches ``st.facing``).

        Normally the shortest sweep to the target heading, in whichever
        direction is closer. Past the donut threshold the car throws in a
        full extra circle — one donut at each end of the screen — at the
        faster drift rate, always the same way round, with the nose anchored
        to its current screen position for the whole spin.
        """
        if target is None:
            target = 0.0 if st.facing == 1 else 180.0

        if donut:
            base = (target - st.yaw) % 360.0
            sweep = base + 360.0
            turn_dir = 1.0
            st._is_donut = True
            if sprite_w_px > 0:
                st._pivot_anchor_x = st.x + _nose_u(st.yaw) * sprite_w_px
        else:
            # shortest rotation to the target heading, either direction
            diff = ((target - st.yaw + 180.0) % 360.0) - 180.0
            if diff == -180.0:
                diff = 180.0               # tie-break matches the old CCW turns
            sweep = abs(diff)
            if sweep < 1.0:
                return
            turn_dir = 1.0 if diff >= 0 else -1.0
            st._is_donut = False

        st._turn_target = target
        st._sweep_left = sweep
        st._turn_rate = DONUT_RATE if donut else TURN_RATE
        st._turn_dir = turn_dir
        st._ang_speed = 0.0
        st.turning = True

    # -------------------------------------------------------------- #
    @staticmethod
    def spin_phase(st: DriveState) -> float:
        """Wheel phase in [0, 1) for frame lookup."""
        return st.spin % 1.0
