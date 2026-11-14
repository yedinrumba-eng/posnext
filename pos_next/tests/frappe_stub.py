"""Import-time stub of ``frappe`` / ``erpnext`` for tests that run without a bench.

``install()`` registers a meta-path finder that serves every module under the missing roots as an
empty package whose attributes are created on demand. It only exists so that modules can be
*imported* (and decorators evaluated) outside a bench; it does not emulate any behaviour.
In a bench (the roots are importable) ``install()`` does nothing and returns ``()``.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import sys
from types import ModuleType
from typing import Any

STUB_ROOTS = ("frappe", "erpnext")


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


class _StubObject:
    """Callable placeholder. A lone callable argument comes back unchanged (decorator usage)."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if len(args) == 1 and not kwargs and callable(args[0]):
            return args[0]
        return _StubObject()

    def __getattr__(self, name: str) -> Any:
        if _is_dunder(name):
            raise AttributeError(name)
        value = _StubObject()
        setattr(self, name, value)
        return value

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(())

    def __bool__(self) -> bool:
        return False


class _StubClassMeta(type):
    """Metaclass of stub classes: unknown class attributes are stub objects (cached)."""

    def __getattr__(cls, name: str) -> Any:
        if _is_dunder(name):
            raise AttributeError(name)
        value = _StubObject()
        setattr(cls, name, value)
        return value


class _StubModule(ModuleType):
    """Module whose missing public attributes are made up and cached."""

    def __getattr__(self, name: str) -> Any:
        if _is_dunder(name):
            raise AttributeError(name)
        if name[:1].isupper():
            bases: tuple[type, ...] = (object,)
            if name.endswith(("Error", "Exception")):
                bases = (Exception,)
            value: Any = _StubClassMeta(name, bases, {"__module__": self.__name__})
        else:
            value = _StubObject()
        setattr(self, name, value)
        return value


class _StubLoader(importlib.abc.Loader):
    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        return _StubModule(spec.name)

    def exec_module(self, module: ModuleType) -> None:
        return None


class _StubFinder(importlib.abc.MetaPathFinder):
    def __init__(self, roots: tuple[str, ...]) -> None:
        self.roots = roots
        self._loader = _StubLoader()

    def find_spec(self, fullname: str, path: Any = None, target: Any = None):  # type: ignore[no-untyped-def]
        if fullname.split(".")[0] not in self.roots:
            return None
        return importlib.machinery.ModuleSpec(fullname, self._loader, is_package=True)


_finder: _StubFinder | None = None
_pos_next_before: set[str] = set()


def install() -> tuple[str, ...]:
    """Stub the roots that are not importable. Returns them (``()`` inside a bench)."""
    global _finder, _pos_next_before
    if _finder is not None:
        return _finder.roots
    missing = tuple(r for r in STUB_ROOTS if importlib.util.find_spec(r) is None)
    if not missing:
        return ()
    _finder = _StubFinder(missing)
    _pos_next_before = {m for m in sys.modules if m == "pos_next" or m.startswith("pos_next.")}
    sys.meta_path.insert(0, _finder)
    return missing


def uninstall() -> None:
    """Remove the finder and, if something was stubbed, forget what was imported through it."""
    global _finder, _pos_next_before
    finder = _finder
    if finder is None:
        return
    if finder in sys.meta_path:
        sys.meta_path.remove(finder)
    for name in list(sys.modules):
        if name.split(".")[0] in finder.roots:
            del sys.modules[name]
        elif (name == "pos_next" or name.startswith("pos_next.")) and name not in _pos_next_before:
            del sys.modules[name]
    _finder = None
    _pos_next_before = set()
