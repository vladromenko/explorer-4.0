"""Compatibility import for installations and artifacts using the original package name."""
import importlib
from importlib.abc import Loader, MetaPathFinder
from importlib.util import find_spec, spec_from_loader
import sys


class _LegacyExplorerImport(MetaPathFinder, Loader):
    @staticmethod
    def _canonical(name):
        return "explorer4" + name[len("explorer3"):]

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith("explorer3."):
            return None
        original = find_spec(self._canonical(fullname))
        if original is not None:
            return spec_from_loader(fullname, self, is_package=original.submodule_search_locations is not None)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        name = module.__name__
        sys.modules[name] = importlib.import_module(self._canonical(name))

    def get_code(self, fullname):
        name = self._canonical(fullname)
        return find_spec(name).loader.get_code(name)


sys.meta_path.insert(0, _LegacyExplorerImport())
