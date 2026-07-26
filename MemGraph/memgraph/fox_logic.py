"""Qt-free behaviour state machine for the fox buddy.

The fox is a live RAM gauge. Given the current RAM %, the drivable span and a
time step, it decides where the fox is, which way it faces, how high it is
hopping off the taskbar, which baked clip is playing and how far through it —
all pure, so the behaviour is unit-testable without a display.

RAM bands (with a little hysteresis so it doesn't flicker on the lines):

* ``< sleep_below`` (75%) — the fox trots to the LEFT corner and curls up
  asleep there (the idle "Survey" clip plays gently, ``asleep`` is True so the
  widget can float a "Zzz").
* ``sleep_below .. run_at`` (75–90%) — it roams the taskbar at a walk.
* ``run_at .. frenzy_at`` (90–95%) — it runs, twice walking pace.
* ``>= frenzy_at`` (95%) — a frenzy: it sprints, and *jumps off the side
  walls* — a quick vertical hop each time it reaches an edge — before tearing
  back the other way.

Everything stays anchored to the taskbar: ``y_off`` is a transient hop height
that always returns to 0, so the fox is never left floating in the desktop.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SLEEP_CLIP = "Survey"
WALK_CLIP = "Walk"
RUN_CLIP = "Run"

HYSTERESIS = 2.0         # RAM % dead-band around each band edge
ARRIVE_PX = 3.0          # close enough to the corner to settle
IDLE_RATE = 0.28         # sleep-idle cycles per second (slow breathing)

# Jump (frenzy wall-hop) physics, in sprite-heights so it scales with size.
JUMP_IMPULSE_H = 3.4     # take-off speed, sprite-heights / second
GRAVITY_H = 11.0         # fall accel, sprite-heights / second^2
JUMP_MAX_H = 0.9         # clamp hop height to <1 sprite so it hugs the bar


@dataclass
class FoxState:
    x: float = 0.0           # widget left edge, px
    facing: int = 1          # +1 faces/moves right, -1 left
    y_off: float = 0.0       # hop height above the taskbar, px (>= 0)
    speed: float = 0.0       # current ground speed, px/s
    clip: str = WALK_CLIP    # baked clip currently playing
    phase: float = 0.0       # 0..1 position within the clip
    asleep: bool = False     # curled up in the corner (draw a "Zzz")
    state: str = "roam"      # "sleep" | "roam" | "run" | "frenzy"
    _vy: float = field(default=0.0, repr=False)   # vertical hop velocity, px/s


class FoxDriver:
    """Advances a :class:`FoxState` through the RAM-driven behaviour bands."""

    def __init__(self, sleep_below: float = 75.0, run_at: float = 90.0,
                 frenzy_at: float = 95.0, walk_stride_frac: float = 0.55) -> None:
        self.sleep_below = float(sleep_below)
        self.run_at = float(run_at)
        self.frenzy_at = float(frenzy_at)
        self.walk_stride_frac = walk_stride_frac

    # -------------------------------------------------------------- #
    def _target_state(self, ram: float, current: str) -> str:
        """Which band ``ram`` falls in, with hysteresis vs the current one."""
        h = HYSTERESIS

        def below(edge: float) -> bool:
            return ram < edge - h
        def above(edge: float) -> bool:
            return ram >= edge + h

        order = ["sleep", "roam", "run", "frenzy"]
        # raw band ignoring hysteresis
        if ram < self.sleep_below:
            raw = "sleep"
        elif ram < self.run_at:
            raw = "roam"
        elif ram < self.frenzy_at:
            raw = "run"
        else:
            raw = "frenzy"
        if raw == current:
            return current
        # only switch once past the edge + hysteresis in the moving direction
        ci, ri = order.index(current), order.index(raw)
        if ri > ci:      # escalating
            edges = [self.sleep_below, self.run_at, self.frenzy_at]
            return raw if above(edges[ci]) else current
        else:            # de-escalating
            edges = [self.sleep_below, self.run_at, self.frenzy_at]
            return raw if below(edges[ci - 1]) else current

    # -------------------------------------------------------------- #
    def step(self, st: FoxState, dt: float, ram: float,
             left: float, right: float, walk_px_s: float,
             sprite_w_px: float, sprite_h_px: float) -> FoxState:
        if right <= left:
            return st
        st.state = self._target_state(ram, st.state)

        # ---- gravity: any active hop always settles back to the bar ----
        if st.y_off > 0.0 or st._vy != 0.0:
            st._vy -= GRAVITY_H * sprite_h_px * dt
            st.y_off += st._vy * dt
            if st.y_off <= 0.0:
                st.y_off = 0.0
                st._vy = 0.0

        if st.state == "sleep":
            return self._sleep(st, dt, left, right, walk_px_s, sprite_w_px)

        st.asleep = False
        if st.state == "roam":
            speed, clip = walk_px_s, WALK_CLIP
        elif st.state == "run":
            speed, clip = walk_px_s * 2.0, RUN_CLIP
        else:                                   # frenzy
            speed, clip = walk_px_s * 3.3, RUN_CLIP

        st.speed = speed
        st.clip = clip
        st.x += st.facing * speed * dt
        if st.x <= left:
            st.x = left
            st.facing = 1
            if st.state == "frenzy":
                self._hop(st, sprite_h_px)
        elif st.x >= right:
            st.x = right
            st.facing = -1
            if st.state == "frenzy":
                self._hop(st, sprite_h_px)

        stride = max(1.0, self.walk_stride_frac * sprite_w_px)
        st.phase = (st.phase + abs(speed) * dt / stride) % 1.0
        return st

    # -------------------------------------------------------------- #
    def _sleep(self, st: FoxState, dt: float, left: float, right: float,
               walk_px_s: float, sprite_w_px: float) -> FoxState:
        st.clip = WALK_CLIP if abs(st.x - left) > ARRIVE_PX else SLEEP_CLIP
        if abs(st.x - left) > ARRIVE_PX:
            # trot to the left corner first (facing the way it travels)
            st.asleep = False
            st.facing = -1 if st.x > left else 1
            st.speed = walk_px_s
            st.x = max(left, st.x - walk_px_s * dt)
            stride = max(1.0, self.walk_stride_frac * sprite_w_px)
            st.phase = (st.phase + walk_px_s * dt / stride) % 1.0
        else:
            # settled: curl up, idle-breathe, show the Zzz
            st.x = left
            st.speed = 0.0
            st.asleep = True
            st.facing = 1
            st.phase = (st.phase + IDLE_RATE * dt) % 1.0
        return st

    # -------------------------------------------------------------- #
    def _hop(self, st: FoxState, sprite_h_px: float) -> None:
        if st.y_off <= 0.0:            # only launch from the ground
            st._vy = JUMP_IMPULSE_H * sprite_h_px
            # cap the arc height so it never climbs off the taskbar strip
            peak = st._vy * st._vy / (2.0 * GRAVITY_H * sprite_h_px)
            if peak > JUMP_MAX_H * sprite_h_px:
                st._vy = (2.0 * GRAVITY_H * sprite_h_px
                          * JUMP_MAX_H * sprite_h_px) ** 0.5
