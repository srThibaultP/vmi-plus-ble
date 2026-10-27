"""Exceptions raised by the client."""

from __future__ import annotations


class VmiPlusError(Exception):
    """Base class of every error raised by this library."""


class VmiPlusConnectionError(VmiPlusError):
    """The unit could not be reached or the connection dropped."""


class VmiPlusTimeoutError(VmiPlusError):
    """The unit did not answer in time."""
