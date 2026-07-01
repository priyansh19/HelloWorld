"""Fixed-size ring buffer used to back the live graph.

Kept dependency-free (pure Python ``collections.deque``) so it is trivially
unit-testable and cheap enough to update several times a second without
allocating.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable


class History:
    """A rolling window of the most recent ``maxlen`` numeric samples.

    Appending beyond capacity discards the oldest sample. Resizing preserves
    the most recent values, which lets the user change the history length at
    runtime without losing the current graph.
    """

    def __init__(self, maxlen: int) -> None:
        if maxlen < 2:
            maxlen = 2
        self._buf: deque[float] = deque(maxlen=maxlen)

    @property
    def maxlen(self) -> int:
        # deque.maxlen is never None here because we always construct with one.
        return self._buf.maxlen  # type: ignore[return-value]

    def append(self, value: float) -> None:
        self._buf.append(float(value))

    def extend(self, values: Iterable[float]) -> None:
        for v in values:
            self.append(v)

    def clear(self) -> None:
        self._buf.clear()

    def values(self) -> list[float]:
        """Oldest-to-newest list suitable for plotting."""
        return list(self._buf)

    def latest(self, default: float = 0.0) -> float:
        return self._buf[-1] if self._buf else default

    def peak(self, default: float = 0.0) -> float:
        return max(self._buf) if self._buf else default

    def average(self, default: float = 0.0) -> float:
        return sum(self._buf) / len(self._buf) if self._buf else default

    def resize(self, maxlen: int) -> None:
        """Change capacity, keeping the newest samples if shrinking."""
        if maxlen < 2:
            maxlen = 2
        if maxlen == self.maxlen:
            return
        self._buf = deque(self._buf, maxlen=maxlen)

    def __len__(self) -> int:
        return len(self._buf)
