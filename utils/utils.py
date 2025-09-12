import os


def resolve_latest_migration() -> str:
    migrations_dir = "migrations"
    if not os.path.exists(migrations_dir):
        raise FileNotFoundError("No migrations directory found.")
    files = [
        f for f in os.listdir(migrations_dir)
        if f.endswith((".yml", ".yaml", ".py"))
    ]
    if not files:
        raise FileNotFoundError("No migration files found in migrations/ directory.")
    files.sort()
    return os.path.join(migrations_dir, files[-1])