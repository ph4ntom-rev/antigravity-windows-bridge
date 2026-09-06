"""Lazy endpoint loading keeps schema discovery free of OS operations."""
import importlib
import threading

_lock = threading.Lock()
_loaded = False


def load_endpoints():
    global _loaded
    with _lock:
        if _loaded:
            return
        for name in ("api_system", "api_fs", "api_ui", "api_memory", "api_input", "api_network", "api_chrome", "api_chrome_ext"):
            importlib.import_module(name)
        _loaded = True
