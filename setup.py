"""
One-time setup script — run as a workspace admin before first deploy.

Usage:
    python setup.py --app-name <your-app-name> --profile <your-profile>

What it does:
    1. Parses app.yaml to read SQL_WAREHOUSE_ID and CONFIG_TABLE
    2. Gets the app's service principal ID
    3. Applies all Stage 1 grants required for the app to start
"""
import argparse
import json
import re
import sys
import time

import requests
from databricks.sdk import WorkspaceClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_app_yaml(path: str = "app.yaml") -> dict:
    """Parse SQL_WAREHOUSE_ID and CONFIG_TABLE from app.yaml without yaml library."""
    with open(path) as f:
        content = f.read()

    def extract(key: str) -> str:
        # Matches:  - name: KEY\n    value: VALUE
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
        "warehouse_id": warehouse_id,
        "config_catalog": parts[0],
        "config_schema":  parts[1],
        "config_table":   parts[2],
    }


def get_sp_id(w: WorkspaceClient, app_name: str) -> str:
    try:
        app = w.apps.get(app_name)
        sp_numeric = getattr(app, "service_principal_id", None)
        if sp_numeric:
            sp = w.service_principals.get(sp_numeric)
            aid = getattr(sp, "application_id", None)
            if aid:
                return str(aid)
    except Exception as e:
        sys.exit(f"ERROR: Could not get service principal for app '{app_name}': {e}")
    sys.exit(f"ERROR: App '{app_name}' has no service_principal_id. Has it been created?")


def run_sql(w: WorkspaceClient, statement: str, warehouse_id: str) -> None:
    host = w.config.host
    token = w.config.authenticate().get("Authorization", "").replace("Bearer ", "")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    resp = requests.post(
        f"{host}/api/2.0/sql/statements",
        headers=headers,
        json={"warehouse_id": warehouse_id, "statement": statement, "wait_timeout": "30s"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    stmt_id = data.get("statement_id")
    while data.get("status", {}).get("state") in ("PENDING", "RUNNING"):
        time.sleep(1)
        data = requests.get(
            f"{host}/api/2.0/sql/statements/{stmt_id}", headers=headers, timeout=30
        ).json()

    state = data.get("status", {}).get("state")
    if state != "SUCCEEDED":
        err = data.get("status", {}).get("error", {})
        raise RuntimeError(f"SQL failed ({state}): {err.get('message', '')}")


def grant_warehouse(w: WorkspaceClient, warehouse_id: str, sp_id: str) -> None:
    host = w.config.host
    token = w.config.authenticate().get("Authorization", "").replace("Bearer ", "")
    resp = requests.patch(
        f"{host}/api/2.0/permissions/warehouses/{warehouse_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"access_control_list": [{"service_principal_name": sp_id, "permission_level": "CAN_USE"}]},
        timeout=30,
    )
    resp.raise_for_status()


def apply_grant(w, warehouse_id, sp_id, stmt: str) -> tuple[bool, str]:
    try:
        run_sql(w, stmt, warehouse_id)
        return True, ""
    except Exception as e:
        return False, str(e)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Apply Stage 1 grants for the tag governance app.")
    parser.add_argument("--app-name",        required=True,  help="Databricks App name")
    parser.add_argument("--profile",         default="DEFAULT", help="Databricks CLI profile")
    parser.add_argument("--target-catalogs", default="",
                        help="Comma-separated catalogs to scan (e.g. cat1,cat2). "
                             "Grants USE SCHEMA on ALL schemas in each catalog so the app "
                             "can read information_schema without per-schema grants.")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Tag Governance — Stage 1 Setup")
    print(f"{'='*60}\n")

    # ── 1. Parse app.yaml
    cfg = parse_app_yaml("app.yaml")
    warehouse_id  = cfg["warehouse_id"]
    config_cat    = cfg["config_catalog"]
    config_schema = cfg["config_schema"]
    print(f"  Warehouse ID  : {warehouse_id}")
    print(f"  Config table  : {config_cat}.{config_schema}.{cfg['config_table']}\n")

    # ── 2. Connect as admin
    w = WorkspaceClient(profile=args.profile)
    print(f"  Connected as  : {w.current_user.me().user_name}")

    # ── 3. Get SP ID
    sp_id = get_sp_id(w, args.app_name)
    print(f"  App SP ID     : {sp_id}\n")

    # ── 4. Build grant list

    # Config-table catalog/schema grants (always required)
    grants_sql = [
        (f"USE CATALOG on `{config_cat}`",
         f"GRANT USE CATALOG ON CATALOG `{config_cat}` TO `{sp_id}`"),
        (f"USE SCHEMA on `{config_cat}`.`{config_schema}`",
         f"GRANT USE SCHEMA ON SCHEMA `{config_cat}`.`{config_schema}` TO `{sp_id}`"),
        (f"CREATE TABLE on `{config_cat}`.`{config_schema}`",
         f"GRANT CREATE TABLE ON SCHEMA `{config_cat}`.`{config_schema}` TO `{sp_id}`"),
        (f"MODIFY on `{config_cat}`.`{config_schema}`",
         f"GRANT MODIFY ON SCHEMA `{config_cat}`.`{config_schema}` TO `{sp_id}`"),
    ]

    # Catalog-level grants for governed catalogs — covers ALL existing schemas at once.
    # After running this, the app can read information_schema for any schema in these
    # catalogs without needing per-schema grants.
    target_catalogs = [c.strip() for c in args.target_catalogs.split(",") if c.strip()]
    for cat in target_catalogs:
        grants_sql.extend([
            (f"USE CATALOG on `{cat}`",
             f"GRANT USE CATALOG ON CATALOG `{cat}` TO `{sp_id}`"),
            (f"APPLY TAG on `{cat}`",
             f"GRANT APPLY TAG ON CATALOG `{cat}` TO `{sp_id}`"),
            (f"USE SCHEMA on ALL SCHEMAS in `{cat}`",
             f"GRANT USE SCHEMA ON ALL SCHEMAS IN CATALOG `{cat}` TO `{sp_id}`"),
            (f"SELECT on ALL TABLES in `{cat}`",
             f"GRANT SELECT ON ALL TABLES IN CATALOG `{cat}` TO `{sp_id}`"),
            (f"MODIFY on ALL TABLES in `{cat}`",
             f"GRANT MODIFY ON ALL TABLES IN CATALOG `{cat}` TO `{sp_id}`"),
        ])

    # ── 5. Apply SQL grants
    print(f"  Applying grants...\n")
    failed = []
    for label, stmt in grants_sql:
        ok, err = apply_grant(w, warehouse_id, sp_id, stmt)
        status = "✓" if ok else "✗"
        print(f"  {status}  {label}")
        if not ok:
            print(f"     └─ {err}")
            failed.append((label, stmt, err))

    # ── 6. Warehouse CAN_USE (REST)
    try:
        grant_warehouse(w, warehouse_id, sp_id)
        print(f"  ✓  CAN_USE on warehouse {warehouse_id}")
    except Exception as e:
        print(f"  ✗  CAN_USE on warehouse {warehouse_id}")
        print(f"     └─ {e}")
        failed.append((f"CAN_USE on warehouse {warehouse_id}", "", str(e)))

    # ── 7. Summary
    print()
    if not failed:
        print("  All grants applied. Any schema in the target catalog(s) is now")
        print("  accessible to the app without further per-schema grants.\n")
        print("  You can now run: databricks apps deploy ...\n")
    else:
        print(f"  {len(failed)} grant(s) failed. Run these manually as a metastore admin:\n")
        for label, stmt, err in failed:
            if stmt:
                print(f"    -- {label} (error: {err})")
                print(f"    {stmt};\n")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
