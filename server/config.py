import os
from databricks.sdk import WorkspaceClient

IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

WAREHOUSE_ID = os.environ.get("SQL_WAREHOUSE_ID", "")
INFO_CATALOG  = os.environ.get("INFO_CATALOG", "")


def get_workspace_client() -> WorkspaceClient:
    if IS_DATABRICKS_APP:
        return WorkspaceClient()
    profile = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
    return WorkspaceClient(profile=profile)


def get_workspace_host() -> str:
    if IS_DATABRICKS_APP:
        host = os.environ.get("DATABRICKS_HOST", "")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        return host
    client = get_workspace_client()
    return client.config.host


def run_sql(statement: str, warehouse_id: str = None, token: str = None) -> list[dict]:
    """Execute SQL via the statement API and return rows as list of dicts."""
    import requests, time

    wh_id = warehouse_id or WAREHOUSE_ID
    host = get_workspace_host()

    if not token:
        w = get_workspace_client()
        auth_headers = w.config.authenticate()
        token = auth_headers.get("Authorization", "").replace("Bearer ", "")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    resp = requests.post(
        f"{host}/api/2.0/sql/statements",
        headers=headers,
        json={
            "warehouse_id": wh_id,
            "statement": statement,
            "wait_timeout": "30s",
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    stmt_id = data.get("statement_id")
    while data.get("status", {}).get("state") in ("PENDING", "RUNNING"):
        time.sleep(1)
        resp = requests.get(
            f"{host}/api/2.0/sql/statements/{stmt_id}",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    state = data.get("status", {}).get("state")
    if state != "SUCCEEDED":
        err = data.get("status", {}).get("error", {})
        raise RuntimeError(f"SQL failed ({state}): {err.get('message', '')}")

    result = data.get("result", {})
    manifest = data.get("manifest", {})
    schema_cols = [c["name"] for c in manifest.get("schema", {}).get("columns", [])]
    rows = result.get("data_array", []) or []

    return [dict(zip(schema_cols, row)) for row in rows]


def get_app_sp_id() -> str | None:
    """Return the UUID application ID of the app's service principal for Unity Catalog grants."""
    import re
    w = get_workspace_client()
    app_name = os.environ.get("DATABRICKS_APP_NAME")
    if app_name:
        try:
            app = w.apps.get(app_name)
            sp_id = getattr(app, "service_principal_id", None)
            if sp_id:
                sp = w.service_principals.get(sp_id)
                aid = getattr(sp, "application_id", None)
                if aid:
                    return str(aid)
        except Exception:
            pass
    try:
        me = w.current_user.me()
        uid = getattr(me, "user_name", "") or ""
        if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", uid):
            return uid
    except Exception:
        pass
    return None
