"""Hermes plugin entry point.

Hermes loads this module and calls `register(plugin_api)` at plugin discovery
time. The API surface across Hermes versions is small but not perfectly
standardized in the spec we were given, so `register` accepts whatever object
Hermes passes and tries the documented binding patterns in order.
"""

from __future__ import annotations

import logging

from .schemas import ALL_SCHEMAS
from .tools import HANDLERS

log = logging.getLogger(__name__)

__version__ = "0.1.0"


def register(plugin_api) -> None:
    """Wire every schema in ALL_SCHEMAS to its handler in HANDLERS.

    Tries the common Hermes plugin-API shapes in order:
      1. plugin_api.register_tool(schema, handler)
      2. plugin_api.add_tool(name, schema, handler)
      3. plugin_api.tools[name] = (schema, handler)
    """
    for schema in ALL_SCHEMAS:
        name = schema["name"]
        handler = HANDLERS.get(name)
        if handler is None:
            log.warning("No handler registered for schema %r; skipping.", name)
            continue
        _bind(plugin_api, name, schema, handler)


def _bind(plugin_api, name: str, schema: dict, handler) -> None:
    if hasattr(plugin_api, "register_tool"):
        plugin_api.register_tool(schema, handler)
        return
    if hasattr(plugin_api, "add_tool"):
        plugin_api.add_tool(name, schema, handler)
        return
    tools_attr = getattr(plugin_api, "tools", None)
    if isinstance(tools_attr, dict):
        tools_attr[name] = (schema, handler)
        return
    raise RuntimeError(
        f"Hermes plugin API surface not recognized; cannot bind tool {name!r}. "
        "Update plugin/__init__.py to match your Hermes version."
    )
