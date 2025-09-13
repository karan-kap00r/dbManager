import importlib.util
import os, yaml, datetime
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class MigrationAction:
    type: str
    payload: Dict[str, Any]

@dataclass
class Migration:
    version: str
    description: str
    actions: List[MigrationAction]

def load_migration_from_file(path: str) -> Migration:
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    version = str(raw.get("version") or datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S"))
    desc = raw.get("description", "")
    actions_raw = raw.get("changes", [])
    actions = [MigrationAction(a_type, payload) for d in actions_raw for a_type, payload in d.items()]
    return Migration(version=version, description=desc, actions=actions)

def load_rename_registry(path: str) -> Dict[str, str]:
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    return raw.get("table_renames", {})


def load_python_migration(path: str):
    """Dynamically load a Python migration file and return (upgrade, downgrade)."""
    spec = importlib.util.spec_from_file_location("migration_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    upgrade = getattr(module, "upgrade", None)
    downgrade = getattr(module, "downgrade", None)

    if not upgrade:
        raise ValueError(f"No upgrade() function found in {path}")

    return upgrade, downgrade
