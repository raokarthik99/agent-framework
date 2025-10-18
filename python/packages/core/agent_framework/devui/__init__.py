# Copyright (c) Microsoft. All rights reserved.

import importlib
from types import ModuleType
from typing import Any

PACKAGE_NAME = "agent_framework_devui"
PACKAGE_EXTRA = "devui"
_module: ModuleType | None = None


def _load_module() -> ModuleType:
    """Import and memoize the implementation package."""
    global _module
    if _module is None:
        try:
            _module = importlib.import_module(PACKAGE_NAME)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The '{PACKAGE_EXTRA}' extra is not installed, please do `pip install agent-framework-{PACKAGE_EXTRA}`"
            ) from exc
    return _module


def __getattr__(name: str) -> Any:
    module = _load_module()
    try:
        return getattr(module, name)
    except AttributeError:
        raise AttributeError(f"Module {PACKAGE_NAME} has no attribute {name}.") from None


def __dir__() -> list[str]:
    module = _load_module()
    exported = getattr(module, "__all__", None)
    if exported is not None:
        return list(exported)
    # Fall back to public attributes if the implementation lacks __all__.
    return [attribute for attribute in dir(module) if not attribute.startswith("_")]
