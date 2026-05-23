"""
Config stored as key-value pairs in a Delta table.
Table path is set via CONFIG_TABLE env var (catalog.schema.table).
Loaded once at app startup and cached in memory.
"""
import json
import os

CONFIG_TABLE = os.environ.get("CONFIG_TABLE", "")

_cached: dict | None = None


def _run(stmt: str):
    from server.config import run_sql, WAREHOUSE_ID
    return run_sql(stmt, warehouse_id=WAREHOUSE_ID)


def _ensure_table():
    if not CONFIG_TABLE:
        raise RuntimeError("CONFIG_TABLE env var is not set.")
    _run(f"""
        CREATE TABLE IF NOT EXISTS {CONFIG_TABLE} (
            key        STRING NOT NULL,
            value      STRING NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    """)


def _load_from_table() -> dict | None:
    try:
        rows = _run(f"SELECT key, value FROM {CONFIG_TABLE}")
        if not rows:
            return None
        cfg: dict = {}
        for row in rows:
            try:
                cfg[row["key"]] = json.loads(row["value"])
            except Exception:
                cfg[row["key"]] = row["value"]
        if "schemas" not in cfg or "tag_columns" not in cfg:
            return None
        return cfg
    except Exception:
        return None


def get_config() -> dict | None:
    """Return the in-memory cached config. None means not yet configured."""
    return _cached


def reload_config():
    global _cached
    _ensure_table()
    _cached = _load_from_table()


def save_config(data: dict):
    """Write each key as a separate row (MERGE for upsert)."""
    _ensure_table()
    for key, value in data.items():
        serialized = json.dumps(value)
        safe = serialized.replace("\\", "\\\\").replace("'", "\\'")
        _run(f"""
            MERGE INTO {CONFIG_TABLE} AS t
            USING (SELECT '{key}' AS key, '{safe}' AS value, CURRENT_TIMESTAMP() AS updated_at) AS s
            ON t.key = s.key
            WHEN MATCHED     THEN UPDATE SET t.value = s.value, t.updated_at = s.updated_at
            WHEN NOT MATCHED THEN INSERT (key, value, updated_at) VALUES (s.key, s.value, s.updated_at)
        """)
    global _cached
    _cached = data
