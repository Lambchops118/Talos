from __future__ import annotations

import importlib
import pkgutil


_DISCOVERED = False
_SKIP_MODULES = {"__init__", "loader", "registry"}


def discover_tools() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return

    package_name = __package__
    if not package_name:
        raise RuntimeError("Tool discovery must run from within the agent_tools package.")

    package = importlib.import_module(package_name)
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name in _SKIP_MODULES or module_info.ispkg:
            continue
        importlib.import_module(f"{package_name}.{module_info.name}")

    _DISCOVERED = True
