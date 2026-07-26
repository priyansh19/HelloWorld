"""Tests for the baked 3D fox walk-cycle atlas."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtGui  # noqa: E402

from memgraph import animal3d as A  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _app():
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    yield app


def test_atlas_present_and_has_walk():
    # The fox atlas ships with the package; if this fails the bake is missing.
    assert A.available()
    assert A.atlas().has(A.WALK_CLIP)


def test_walk_frames_are_distinct():
    a = A.atlas()
    n = a.frame_count(A.WALK_CLIP)
    assert n >= 4
    imgs = [A.frame_image(120, A.WALK_CLIP, i / n) for i in range(n)]
    assert all(im is not None for im in imgs)
    # a real walk cycle => not every frame identical
    assert len({im.constBits().tobytes() for im in imgs}) > 1


def test_frames_have_transparent_background():
    img = A.frame_image(120, A.WALK_CLIP, 0.0)
    assert img.pixelColor(0, 0).alpha() == 0


def test_runs_when_stressed_walks_when_calm():
    a = A.atlas()
    calm = A.clip_for_stress(0.0)
    assert calm == A.WALK_CLIP
    if a.has(A.RUN_CLIP):
        assert A.clip_for_stress(A.RUN_STRESS) == A.RUN_CLIP
        assert A.clip_for_stress(1.0) == A.RUN_CLIP


def test_sprite_units_follow_atlas_aspect():
    w, h = A.sprite_units()
    assert w == A.SPRITE_W
    assert h >= 1
    # the fox is longer than tall, so width should exceed height
    assert w > h


def test_frame_scaled_to_requested_width():
    img = A.frame_image(200, A.WALK_CLIP, 0.25)
    # rendered at 2x for HiDPI, with devicePixelRatio 2
    assert img.devicePixelRatio() == 2.0
    assert img.width() == 400


def test_phase_wraps():
    a = A.atlas()
    n = a.frame_count(A.WALK_CLIP)
    # phase 1.0 wraps back to frame 0
    assert A.frame_image(120, A.WALK_CLIP, 0.0) is \
        A.frame_image(120, A.WALK_CLIP, 1.0)
