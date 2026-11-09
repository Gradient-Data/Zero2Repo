"""Shared pytest reporting configuration."""


def pytest_configure(config):
    """Report every setup, call and teardown duration, including zero."""
    config.option.durations = 0
    config.option.durations_min = 0
