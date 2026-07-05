"""moot — CLI + MCP adapters for Moot agent teams."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mootup")
except PackageNotFoundError:
    __version__ = "0.0.0"
