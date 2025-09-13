__version__ = "0.1.0"

# Import the main functions for programmatic access
from .commands import set_database_url, get_database_url

__all__ = [
    "set_database_url",
    "get_database_url",
    "__version__"
]