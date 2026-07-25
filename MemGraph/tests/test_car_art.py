"""Tests for the vector Mustang art.

Qt raster rendering needs a QGuiApplication, so these tests build one on the
offscreen platform.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtGui  # noqa: E402

from memgraph import car_art as A  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _app():
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    yield app


def test_frames_render_non_empty():
    for i in range(A.FRAMES):
        img = A.render_image(240, i)
        assert not img.isNull()
        assert img.width() > 0 and img.height() > 0


def test_aspect_matches_design_space():
    img = A.render_image(360, 0)
    # width/height ratio should track the design box (allowing HiDPI scaling)
    ratio = img.width() / img.height()
    assert abs(ratio - A.DESIGN_W / A.DESIGN_H) < 0.05


def test_render_is_cached():
    a = A.render_image(200, 3)
    b = A.render_image(200, 3)
    assert a is b


def test_wheels_actually_spin():
    # Different frames must produce different pixels, or the car looks static.
    a = A.render_image(240, 0)
    b = A.render_image(240, 2)
    assert a != b


def test_has_transparent_background():
    img = A.render_image(240, 0)
    assert img.pixelColor(0, 0).alpha() == 0


def test_car_is_exempt_from_the_ram_tint():
    # Smoke conveys RAM stress for the car, so nothing reddens.
    assert set(A.PALETTE) <= A.TINT_EXEMPT


def test_exhaust_within_sprite_bounds():
    ex, ey = A.EXHAUST
    assert 0 <= ex < A.SPRITE_W
    assert 0 <= ey < A.SPRITE_H


def test_supersampling_beats_the_old_cell_grid_by_1000x():
    # The retired character-grid car rendered 60x38 == 2280 cells per frame.
    # At the default widget width the vector car rasterises >1000x that many.
    default_width = int(A.SPRITE_W * 4.05)
    assert A.samples_per_frame(default_width) > 1000 * 2280


def test_overlays_are_noop():
    rows = ["abc"]
    assert A.apply_overlays(rows, shades=True, blink=True) == rows
