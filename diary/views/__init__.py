import pkgutil
import importlib
import sys
import inspect
from pathlib import Path

# Get the current package path
package_path = Path(__file__).parent
package_name = __name__

# Automatically import all modules in views/
for _, module_name, is_pkg in pkgutil.iter_modules([str(package_path)]):
    if not is_pkg and module_name != "__init__":
        full_module_name = f"{package_name}.{module_name}"
        module = importlib.import_module(full_module_name)

        # Import all public attributes (functions/classes) to the package namespace
        for attr_name in dir(module):
            if not attr_name.startswith("_"):  # skip private/internal
                attr = getattr(module, attr_name)
                if inspect.isfunction(attr) or inspect.isclass(attr):
                    globals()[attr_name] = attr

# Optional: expose only non-private names via __all__
__all__ = [k for k in globals() if not k.startswith("_") and (inspect.isfunction(globals()[k]) or inspect.isclass(globals()[k]))]
