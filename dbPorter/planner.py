from typing import List, Dict, Any
from .migration_loader import Migration

def plan_migration(migration: Migration, rename_registry: Dict[str, str]) -> List[Dict[str, Any]]:
    planned = []
    for act in migration.actions:
        if act.type == "rename_table":
            src = act.payload["from"]
            dst = act.payload["to"]
            planned.append({"op": "rename_table", "from": src, "to": dst})
        elif act.type == "split_column":
            planned.append({"op": "split_column", **act.payload})
        else:
            planned.append({"op": "raw", "type": act.type, "payload": act.payload})
    return planned
