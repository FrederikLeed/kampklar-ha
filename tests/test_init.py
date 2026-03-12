"""Tests for the KampKlar integration."""

from custom_components.kampklar.const import DOMAIN


def test_domain() -> None:
    """Test that the domain is set correctly."""
    assert DOMAIN == "kampklar"
