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

TURN_RATE = 460.0        # deg/s the yaw sweeps during a turn-around
PARK_HYSTERESIS = 2.0    # RAM % band around park_below
ARRIVE_PX = 3.0          # close enough to the parking spot to stop

# Speed multiplier vs RAM once driving: eases in just past the park line and
# roughly doubles by the time memory is critical.
def _ram_speed_mult(ram_pct: float, park_below: float) -> float:
    over = max(0.0, ram_pct - park_below)
    return 1.0 + min(1.6, over * 0.032)          # +0.032x per % over the line


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


class Driver:
    """Advances a :class:`DriveState` through park/drift/turn behaviour."""

    def __init__(self, park_below: float = 50.0,
                 wheel_circumference_px: float = 46.0) -> None:
        self.park_below = float(park_below)
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

        # ---- turning: sweep yaw through the ring, wheels still spinning
        if st.turning:
            st.yaw = (st.yaw + TURN_RATE * dt) % 360.0
            remaining = (st._turn_target - st.yaw) % 360.0
            if remaining <= TURN_RATE * dt * 1.5:
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
        st.speed = cruise_px_s * _ram_speed_mult(ram_pct, self.park_below)
        st.x += st.facing * st.speed * dt
        st.spin += st.speed * dt / self.wheel_circ
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
    def _begin_turn_if_needed(self, st: DriveState) -> None:
        target = 0.0 if st.facing == 1 else 180.0
        if not math.isclose((st.yaw - target) % 360.0, 0.0, abs_tol=1.0):
            st._turn_target = target
            st.turning = True

    # -------------------------------------------------------------- #
    @staticmethod
    def spin_phase(st: DriveState) -> float:
        """Wheel phase in [0, 1) for frame lookup."""
        return st.spin % 1.0
