"""
One-time setup script — run as a workspace admin after creating the app,
before or after the first deploy.

Usage:
    python setup.py --app-name <your-app-name> --profile <your-profile>

    # Also grant access to governed catalog(s):
    python setup.py --app-name <your-app-name> --profile <your-profile> \
        --target-catalogs cat1,cat2

What it does:
    1. Parses app.yaml to read SQL_WAREHOUSE_ID and CONFIG_TABLE
    2. Gets the app's service principal UUID
    3. Applies all grants the app needs via SQL + UC REST API

Dependencies:
    pip install databricks-sdk
    (urllib.request is used for HTTP — no 'requests' package needed)
"""
import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error

from databricks.sdk import WorkspaceClient


# ── HTTP helper (stdlib only) ──────────────────────────────────────────────────

def _api(host: str, token: str, method: str, path: str, body: dict = None):
    url     = f"{host}{path}"
    data    = json.dumps(body).encode() if body else None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req     = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


# ── app.yaml parser ───────────────────────────────────────────────────────────

def parse_app_yaml(path: str = "app.yaml") -> dict:
    with open(path) as f:
        content = f.read()

    def extract(key: str) -> str:
        m = re.search(rf"name:\s*{key}\s*\n\s*value:\s*(.+)", content)
        return m.group(1).strip().strip('"').strip("'") if m else ""

    warehouse_id = extract("SQL_WAREHOUSE_ID")
    config_table = extract("CONFIG_TABLE")

    if not warehouse_id:
        sys.exit("ERROR: SQL_WAREHOUSE_ID not found in app.yaml env section.")
    if not config_table:
        sys.exit("ERROR: CONFIG_TABLE not found in app.yaml env section.")
    parts = config_table.split(".")
    if len(parts) != 3:
        sys.exit(f"ERROR: CONFIG_TABLE must be catalog.schema.table, got: {config_table}")
    return {
        "warehouse_id":  warehouse_id,
        "config_catalog": parts[0],
        "config_schema":  parts[1],
        "config_table":   parts[2],
    }


# ── SP lookup ─────────────────────────────────────────────────────────────────

def get_sp_uuid(w: WorkspaceClient, app_name: str) -> str:
    try:
        app        = w.apps.get(app_name)
        sp_numeric = getattr(app, "service_principal_id", None)
        if sp_numeric:
            sp  = w.service_principals.get(sp_numeric)
            aid = getattr(sp, "application_id", None)
            if aid:
                return str(aid)
    except Exception as e:
        sys.exit(f"ERROR: Could not get service principal for app '{app_name}': {e}")
    sys.exit(f"ERROR: App '{app_name}' has no service_principal_id. Has it been created yet?")


# ── SQL grant (via statement execution API) ───────────────────────────────────

def sql_grant(host: str, token: str, warehouse_id: str, label: str, stmt: str) -> tuple[bool, str]:
    resp    = _api(host, token, "POST", "/api/2.0/sql/statements",
                   {"warehouse_id": warehouse_id, "statement": stmt, "wait_timeout": "30s"})
    stmt_id = resp.get("statement_id")
    state   = resp.get("status", {}).get("state", "ERROR")

    while state in ("PENDING", "RUNNING") and stmt_id:
        time.sleep(1)
        resp  = _api(host, token, "GET", f"/api/2.0/sql/statements/{stmt_id}")
        state = resp.get("status", {}).get("state", "ERROR")

    if state == "SUCCEEDED":
        return True, ""
    msg = resp.get("status", {}).get("error", {}).get("message") or resp.get("message", "unknown")
    return False, msg


# ── UC REST API grant (for catalog/schema-level bulk privileges) ──────────────
#
# GRANT ... ON ALL SCHEMAS/TABLES IN CATALOG is not supported by the statement
# execution API. The UC permissions REST API is used instead and achieves the
# same effect: privileges on the securable object are inherited by all children.

def uc_grant(host: str, token: str, securable_type: str, full_name: str,
             sp_id: str, privileges: list[str]) -> tuple[bool, str]:
    resp = _api(host, token, "PATCH",
                f"/api/2.1/unity-catalog/permissions/{securable_type}/{full_name}",
                {"changes": [{"principal": sp_id, "add": privileges}]})
    if "error_code" in resp or ("message" in resp and "error" in resp.get("message", "").lower()):
        return False, resp.get("message", "unknown")
    return True, ""


def list_schemas(host: str, token: str, catalog: str) -> list[str]:
    schemas = []
    token_  = None
    while True:
        path = f"/api/2.1/unity-catalog/schemas?catalog_name={catalog}&max_results=200"
        if token_:
            path += f"&page_token={token_}"
        resp    = _api(host, token, "GET", path)
        schemas += [s["name"] for s in resp.get("schemas", [])]
        token_  = resp.get("next_page_token")
        if not token_:
            break
    return schemas


# ── Warehouse CAN_USE ─────────────────────────────────────────────────────────

def grant_warehouse(host: str, token: str, warehouse_id: str, sp_id: str) -> tuple[bool, str]:
    resp = _api(host, token, "PATCH", f"/api/2.0/permissions/warehouses/{warehouse_id}",
                {"access_control_list": [{"service_principal_name": sp_id, "permission_level": "CAN_USE"}]})
    if "object_id" in resp or "access_control_list" in resp:
        return True, ""
    return False, resp.get("message", "unknown")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Apply grants for the UC Tag Governance app.")
    parser.add_argument("--app-name",        required=True,  help="Databricks App name")
    parser.add_argument("--profile",         default="DEFAULT", help="Databricks CLI profile (~/.databrickscfg)")
    parser.add_argument("--target-catalogs", default="",
                        help="Comma-separated catalogs the app will govern (e.g. cat1,cat2). "
                             "Grants USE_SCHEMA on every schema and SELECT+MODIFY at catalog level.")
    args = parser.parse_args()

    SEP = "=" * 62
    print(f"\n{SEP}")
    print("  UC Tag Governance — One-Time Setup")
    print(f"{SEP}\n")

    # 1. Parse app.yaml
    cfg          = parse_app_yaml("app.yaml")
    warehouse_id = cfg["warehouse_id"]
    config_cat   = cfg["config_catalog"]
    config_sch   = cfg["config_schema"]
    print(f"  Warehouse    : {warehouse_id}")
    print(f"  Config table : {config_cat}.{config_sch}.{cfg['config_table']}")

    # 2. Connect
    w     = WorkspaceClient(profile=args.profile)
    host  = w.config.host
    token = w.config.authenticate().get("Authorization", "").replace("Bearer ", "")
    print(f"  Connected as : {w.current_user.me().user_name}")

    # 3. SP UUID
    sp_id = get_sp_uuid(w, args.app_name)
    print(f"  App SP UUID  : {sp_id}\n")

    failed = []

    def run(label, fn, *a, **kw):
        ok, err = fn(*a, **kw)
        print(f"  {'✓' if ok else '✗'}  {label}")
        if not ok:
            print(f"     └─ {err}")
            failed.append((label, err))

    # 4. Config-table grants (always applied)
    print(f"  Config-table grants ({config_cat}.{config_sch})...")
    run(f"USE CATALOG on `{config_cat}`",
        sql_grant, host, token, warehouse_id,
        f"USE CATALOG on `{config_cat}`",
        f"GRANT USE CATALOG ON CATALOG `{config_cat}` TO `{sp_id}`")
    run(f"USE SCHEMA on `{config_cat}`.`{config_sch}`",
        sql_grant, host, token, warehouse_id,
        f"USE SCHEMA on `{config_cat}`.`{config_sch}`",
        f"GRANT USE SCHEMA ON SCHEMA `{config_cat}`.`{config_sch}` TO `{sp_id}`")
    run(f"CREATE TABLE on `{config_cat}`.`{config_sch}`",
        sql_grant, host, token, warehouse_id,
        f"CREATE TABLE on `{config_cat}`.`{config_sch}`",
        f"GRANT CREATE TABLE ON SCHEMA `{config_cat}`.`{config_sch}` TO `{sp_id}`")
    run(f"MODIFY on `{config_cat}`.`{config_sch}`",
        sql_grant, host, token, warehouse_id,
        f"MODIFY on `{config_cat}`.`{config_sch}`",
        f"GRANT MODIFY ON SCHEMA `{config_cat}`.`{config_sch}` TO `{sp_id}`")

    # 5. Governed catalog grants
    target_catalogs = [c.strip() for c in args.target_catalogs.split(",") if c.strip()]
    for cat in target_catalogs:
        print(f"\n  Governed catalog grants (`{cat}`)...")

        run(f"USE CATALOG on `{cat}`",
            sql_grant, host, token, warehouse_id,
            f"USE CATALOG on `{cat}`",
            f"GRANT USE CATALOG ON CATALOG `{cat}` TO `{sp_id}`")

        run(f"APPLY TAG on `{cat}`",
            sql_grant, host, token, warehouse_id,
            f"APPLY TAG on `{cat}`",
            f"GRANT APPLY TAG ON CATALOG `{cat}` TO `{sp_id}`")

        # USE SCHEMA must be granted per-schema (bulk SQL syntax unsupported via
        # statement API). Enumerate schemas via UC REST API and grant individually.
        print(f"     Fetching schemas in `{cat}`...")
        schemas = list_schemas(host, token, cat)
        print(f"     Found {len(schemas)} schema(s). Granting USE SCHEMA...")
        sch_ok = sch_fail = 0
        for schema in schemas:
            ok, err = uc_grant(host, token, "schema", f"{cat}.{schema}", sp_id, ["USE_SCHEMA"])
            if ok:
                sch_ok += 1
            else:
                sch_fail += 1
                print(f"     ✗  USE SCHEMA on `{cat}`.`{schema}` — {err}")
        print(f"  {'✓' if not sch_fail else '~'}  USE SCHEMA on all schemas ({sch_ok} ok, {sch_fail} failed)")
        if sch_fail:
            failed.append((f"USE SCHEMA on some schemas in `{cat}`", f"{sch_fail} schema(s) failed"))

        # SELECT + MODIFY granted at catalog level via UC REST API — inherited by
        # all schemas and tables, equivalent to ON ALL TABLES IN CATALOG.
        run(f"SELECT + MODIFY at catalog level on `{cat}`",
            uc_grant, host, token, "catalog", cat, sp_id, ["SELECT", "MODIFY"])

    # 6. Warehouse CAN_USE
    print(f"\n  Warehouse grant...")
    run(f"CAN_USE on warehouse {warehouse_id}",
        grant_warehouse, host, token, warehouse_id, sp_id)

    # 7. Summary
    print()
    if not failed:
        print("  All grants applied successfully.")
        print("  The app's service principal can now read information_schema,")
        print("  apply tags, and write comments on tables in the governed catalog(s).")
        print(f"\n  Next step: databricks apps deploy {args.app_name} --source-code-path <path>\n")
    else:
        print(f"  {len(failed)} grant(s) failed — apply these manually as a metastore admin:\n")
        for label, err in failed:
            print(f"    ✗  {label}")
            print(f"       {err}\n")

    print(f"{SEP}\n")


if __name__ == "__main__":
    main()
