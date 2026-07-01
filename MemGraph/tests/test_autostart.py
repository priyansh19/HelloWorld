import sys

from memgraph import autostart


def test_launch_command_nonempty():
    cmd = autostart.current_launch_command()
    assert cmd
    assert cmd.startswith('"')


def test_noop_safe_off_windows():
    # On non-Windows the functions must never raise and report disabled.
    if not sys.platform.startswith("win"):
        assert autostart.is_enabled() is False
        assert autostart.enable() is False
        assert autostart.disable() is False
        assert autostart.apply(True) is False
        assert autostart.apply(False) is False
