"""Utils"""

from importlib import resources
from pathlib import Path


static_dir = resources.files("mcsc") / "static"


def get_static_path(filename: str) -> Path:
    """Restituisce il path a un file statico nel package"""
    return resources.files("mcsc.static") / filename


def load_static_file(filename: str, mode: str = "rb"):
    """Carica un file statico come contenuto"""
    path = get_static_path(filename)
    with path.open(mode) as f:
        return f.read()


class Singleton:
    """Singleton class"""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Singleton, cls).__new__(cls)
        return cls._instance
