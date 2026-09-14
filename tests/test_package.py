"""Basic tests for the initial package scaffold."""

import hydrokg


def test_package_has_version() -> None:
    assert hydrokg.__version__ == "0.0.0"
