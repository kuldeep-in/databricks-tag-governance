import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from server.config import run_sql, WAREHOUSE_ID, get_workspace_host, get_workspace_client, get_app_sp_id
from server.config_store import CONFIG_TABLE, get_config, save_config, reload_config

router = APIRouter()

# Catalog that holds the config table (derived from CONFIG_TABLE env var)
_CONFIG_CATALOG = CONFIG_TABLE.split(".")[0] if CONFIG_TABLE else ""
_CONFIG_SCHEMA  = CONFIG_TABLE.split(".")[1] if CONFIG_TABLE and CONFIG_TABLE.count(".") >= 2 else "default"


class ConfigPayload(BaseModel):
    schemas:     list[dict]
    tag_columns: list[str]
    exceptions:  list[dict]


@router.get("/config")
def api_get_config():
    cfg = get_config()
    if cfg is None:
        return {"schemas": [], "tag_columns": [], "exceptions": [], "configured": False}
    return {**cfg, "configured": True}


def _apply_grants(schemas: list[dict], user_token: str = None) -> list[dict]:
    sp_id = get_app_sp_id()
    if not sp_id:
        return [{"sql": "(could not determine service principal ID — grants skipped)", "status": "skipped"}]

    results = []

    def try_sql(stmt: str):
        try:
            # Use end-user token — they have MANAGE GRANTS; the SP does not
            run_sql(stmt, warehouse_id=WAREHOUSE_ID, token=user_token)
            results.append({"sql": stmt, "status": "ok"})
        except Exception as e:
            results.append({"sql": stmt, "status": "failed", "error": str(e)})

    # Config table schema grants
    if _CONFIG_CATALOG and _CONFIG_SCHEMA:
        for stmt in [
            f"GRANT USE SCHEMA ON SCHEMA `{_CONFIG_CATALOG}`.`{_CONFIG_SCHEMA}` TO `{sp_id}`",
            f"GRANT CREATE TABLE ON SCHEMA `{_CONFIG_CATALOG}`.`{_CONFIG_SCHEMA}` TO `{sp_id}`",
            f"GRANT MODIFY ON SCHEMA `{_CONFIG_CATALOG}`.`{_CONFIG_SCHEMA}` TO `{sp_id}`",
        ]:
            try_sql(stmt)

    # Per-catalog grants — USE CATALOG + APPLY TAG + broad read/modify on all schemas.
    # Granting at catalog level means every schema in the catalog is immediately
    # accessible without needing separate per-schema grants.
    for catalog in {s["catalog"] for s in schemas}:
        try_sql(f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{sp_id}`")
        try_sql(f"GRANT APPLY TAG ON CATALOG `{catalog}` TO `{sp_id}`")
        try_sql(f"GRANT USE SCHEMA ON ALL SCHEMAS IN CATALOG `{catalog}` TO `{sp_id}`")
        try_sql(f"GRANT SELECT ON ALL TABLES IN CATALOG `{catalog}` TO `{sp_id}`")
        try_sql(f"GRANT MODIFY ON ALL TABLES IN CATALOG `{catalog}` TO `{sp_id}`")

    # Warehouse CAN_USE via REST
    try:
        host = get_workspace_host()
        token_for_rest = user_token
        if not token_for_rest:
            w = get_workspace_client()
            token_for_rest = w.config.authenticate().get("Authorization", "").replace("Bearer ", "")
        resp = requests.patch(
            f"{host}/api/2.0/permissions/warehouses/{WAREHOUSE_ID}",
            headers={"Authorization": f"Bearer {token_for_rest}", "Content-Type": "application/json"},
            json={"access_control_list": [{"service_principal_name": sp_id, "permission_level": "CAN_USE"}]},
            timeout=30,
        )
        resp.raise_for_status()
        results.append({"sql": f"PATCH warehouse/{WAREHOUSE_ID}: CAN_USE → {sp_id}", "status": "ok"})
    except Exception as e:
        results.append({"sql": f"PATCH warehouse/{WAREHOUSE_ID}: CAN_USE → {sp_id}", "status": "failed", "error": str(e)})

    return results


@router.put("/config")
def api_put_config(payload: ConfigPayload, request: Request):
    data = {"schemas": payload.schemas, "tag_columns": payload.tag_columns, "exceptions": payload.exceptions}
    try:
        save_config(data)
        reload_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # X-Forwarded-Access-Token carries the logged-in user's OAuth token in Databricks Apps.
    # Using it for grants means the admin's MANAGE GRANTS privilege is used, not the SP's.
    user_token = request.headers.get("X-Forwarded-Access-Token")
    grants = _apply_grants(payload.schemas, user_token=user_token)
    return {
        "status": "saved",
        "grants": grants,
        "grants_failed": any(g["status"] == "failed" for g in grants),
    }
