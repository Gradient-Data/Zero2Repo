# feature: F00
"""Retain replay collection identities and all setup/call/teardown timings."""


def pytest_configure(config):
    config.option.durations = 0
    config.option.durations_min = 0


def pytest_collection_finish(session):
    reporter = session.config.pluginmanager.get_plugin('terminalreporter')
    reporter.write_sep('=', 'replay collection inventory')
    for item in session.items:
        reporter.write_line(item.nodeid)
