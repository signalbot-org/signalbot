import importlib.metadata

from signalbot import __version__
from signalbot._utils.version import package_version


def test_installed_package_version():
    assert __version__ == importlib.metadata.version("signalbot")


def test_uninstalled_package_falls_back_to_zero_version():
    """E.g. when running from a source checkout that was never installed."""
    assert package_version("signalbot-not-installed") == "0.0.0"
