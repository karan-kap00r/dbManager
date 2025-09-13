from typing import List, Optional, Dict, Any
from sqlalchemy.engine import Connection
from sqlalchemy import text

def exec_rename_table(conn: Connection, frm: str, to: str):
    conn.execute(text(f"ALTER TABLE {frm} RENAME TO {to};"))

def exec_split_column(conn: Connection, table: str, column: str, into: List[str], transform: Optional[str]):
    # prototype split
    for c in into:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {c} TEXT;"))

def exec_raw_operation(conn: Connection, raw: Dict[str, Any]):
    op_type = raw.get("type")
    payload = raw.get("payload")

    if op_type == "create_table":
        table_name = payload["table"]
        cols = []
        for col in payload.get("columns", []):
            col_def = f"{col['name']} {col['type']}"
            if not col.get("nullable", True):
                col_def += " NOT NULL"
            if col.get("primary_key", False):
                col_def += " PRIMARY KEY"
            cols.append(col_def)
        sql = f"CREATE TABLE {table_name} ({', '.join(cols)});"
        conn.execute(text(sql))

    elif op_type == "drop_table":
        conn.execute(text(f"DROP TABLE IF EXISTS {payload['table']};"))

    elif op_type == "add_column":
        sql = f"ALTER TABLE {payload['table']} ADD COLUMN {payload['column']} {payload['type']};"
        conn.execute(text(sql))

    elif op_type == "drop_column":
        conn.execute(text(f"ALTER TABLE {payload['table']} DROP COLUMN {payload['column']};"))

    elif op_type == "add_index":
        sql = f"CREATE INDEX {payload['name']} ON {payload['table']} ({', '.join(payload['columns'])});"
        conn.execute(text(sql))

    elif op_type == "drop_index":
        sql = f"DROP INDEX {payload['name']} ON {payload['table']};"
        conn.execute(text(sql))

    else:
        print("⚠️ Unknown raw operation:", op_type)
