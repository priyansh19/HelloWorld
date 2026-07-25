"""Qt-free driving logic for the Mustang buddy.

The widget feeds this a time step, the live RAM %, and the drivable span; it
answers where the car is, which way it points (continuous yaw for the baked 3D
frame ring) and how fast the wheels are rolling. Keeping it pure makes the
park/drift behaviour unit-testable without a display.

Behaviour spec:

* RAM below ``park_below`` → the car drives to the nearest screen corner,
  stops, and sits there with the wheels still (a small hysteresis band stops
  it flapping when RAM hovers on the line).
* RAM above the line → it drifts back and forth along the taskbar, speed
  climbing with RAM.
* At each edge (or when unparking toward the other side) it *turns around* by
  sweeping yaw through the ring — the drift — with the wheels kept spinning
  through the slide, like a real burnout turn.
* Wheel spin rate is proportional to road speed at all times.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

TURN_RATE = 620.0        # deg/s the yaw sweeps during a turn-around
DONUT_RATE = 760.0       # deg/s during a donut — a drift spin is quicker
PARK_HYSTERESIS = 2.0    # RAM % band around park_below
ARRIVE_PX = 3.0          # close enough to the parking spot to stop


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
    speed: float = 0.0        # current speed, px/s (for the smoke/tests)
    park_side: int = 0        # -1 left corner, +1 right corner, 0 undecided
    _turn_target: float = field(default=0.0, repr=False)
    _sweep_left: float = field(default=0.0, repr=False)   # degrees still to turn
    _turn_rate: float = field(default=TURN_RATE, repr=False)


class Driver:
    """Advances a :class:`DriveState` through park/drift/turn behaviour."""

    def __init__(self, park_below: float = 50.0, donut_above: float = 80.0,
                 wheel_circumference_px: float = 46.0) -> None:
        self.park_below = float(park_below)
        self.donut_above = float(donut_above)
        self.wheel_circ = max(8.0, wheel_circumference_px)

    # -------------------------------------------------------------- #
    def step(self, st: DriveState, dt: float, ram_pct: float,
             left: float, right: float, cruise_px_s: float) -> DriveState:
        """One simulation step of ``dt`` seconds. Mutates and returns ``st``."""
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

        # ---- turning: sweep yaw through the ring, wheels still spinning.
        # A donut is the same sweep plus a full extra 360 revolution.
        if st.turning:
            d = st._turn_rate * dt
            st.yaw = (st.yaw + d) % 360.0
            st._sweep_left -= d
            if st._sweep_left <= 0.0:
                st.yaw = st._turn_target
                st.turning = False
            # burnout: wheels churn through the slide at the pre-turn rate
            st.spin += max(st.speed, cruise_px_s) * dt / self.wheel_circ
            return st

        # ---- parked: creep to the corner, then sit still --------------
        if st.parked:
            target = left if st.park_side < 0 else right
            delta = target - st.x
            if abs(delta) > ARRIVE_PX:
                want = 1 if delta > 0 else -1
                if want != st.facing:
                    st.facing = want
                    self._begin_turn_if_needed(st)
                    return st
                st.speed = cruise_px_s
                st.x += st.facing * st.speed * dt
                st.spin += st.speed * dt / self.wheel_circ
            else:
                st.x = target
                st.speed = 0.0            # wheels stop with the car
            return st

        # ---- drifting back and forth ---------------------------------
        st.speed = cruise_px_s * _ram_speed_mult(ram_pct, self.park_below,
                                                 self.donut_above)
        st.x += st.facing * st.speed * dt
        st.spin += st.speed * dt / self.wheel_circ
        donut = ram_pct >= self.donut_above
        if st.x <= left:
            st.x = left
            st.facing = 1
            self._begin_turn_if_needed(st, donut=donut)
        elif st.x >= right:
            st.x = right
            st.facing = -1
            self._begin_turn_if_needed(st, donut=donut)
        return st

    # -------------------------------------------------------------- #
    def _begin_turn_if_needed(self, st: DriveState, donut: bool = False) -> None:
        """Start a yaw sweep toward the new heading.

        Normally the shortest CCW sweep to face the other way; past the donut
        threshold the car throws in a full extra circle — one donut at each
        end of the screen — at the faster drift rate.
        """
        target = 0.0 if st.facing == 1 else 180.0
        base = (target - st.yaw) % 360.0
        if base < 1.0 and not donut:
            return
        st._turn_target = target
        st._sweep_left = base + (360.0 if donut else 0.0)
        st._turn_rate = DONUT_RATE if donut else TURN_RATE
        st.turning = True

    # -------------------------------------------------------------- #
    @staticmethod
    def spin_phase(st: DriveState) -> float:
        """Wheel phase in [0, 1) for frame lookup."""
        return st.spin % 1.0
