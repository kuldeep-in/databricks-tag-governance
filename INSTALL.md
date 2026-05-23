# Installation Guide — UC Tag Governance App

A step-by-step guide to deploying the Unity Catalog Tag Governance Databricks App.

> **No build step required.** The app is pure Python (Dash + Gunicorn).
> No Node.js, npm, or frontend compilation needed.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Databricks CLI ≥ 0.229.0 | `brew install databricks/tap/databricks` or [download](https://docs.databricks.com/dev-tools/cli/install.html) |
| Python ≥ 3.10 | Required to run `setup.py` locally |
| `databricks-sdk` Python package | `pip install databricks-sdk` — used only by `setup.py`, not the app itself |
| Workspace admin or metastore admin | Needed to create the app and run grants |
| Unity Catalog metastore | Tables must be in UC-managed catalogs |
| SQL Warehouse | Serverless or classic; used for all SQL queries at runtime |

---

## Step 1 — Authenticate the Databricks CLI

```bash
databricks auth login \
  --host https://<your-workspace>.azuredatabricks.net \
  --profile <your-profile>
```

Verify:

```bash
databricks auth profiles
```

---

## Step 2 — Get the source code

```bash
git clone <repo-url>
cd databricks-tag-governance
```

---

## Step 3 — Configure `app.yaml`

Open `app.yaml` and fill in the three placeholder values:

```yaml
command:
  - "gunicorn"
  - "--bind=0.0.0.0:8000"
  - "--workers=1"
  - "--timeout=120"
  - "app:server"

env:
  - name: SQL_WAREHOUSE_ID
    value: <your-warehouse-id>
    # ↑ Found in SQL Warehouses UI → Connection Details tab

  - name: CONFIG_TABLE
    value: <your-catalog>.default.uc_tag_governance_config
    # ↑ Delta table where the app persists its own configuration.
    #   The catalog and schema must already exist.
    #   The table is created automatically on first save.

  - name: INFO_CATALOG
    value: <your-catalog>
    # ↑ The catalog whose information_schema is queried for table/tag metadata.
    #   Usually the same catalog as CONFIG_TABLE, but can differ.
```

---

## Step 4 — Upload source files to Databricks Workspace

```bash
DEST="/Workspace/Users/<your-email>/databricks-tag-governance"
PROFILE="<your-profile>"

databricks workspace import-dir . "$DEST" --profile "$PROFILE" --overwrite
```

This uploads the complete directory tree:

```
databricks-tag-governance/
├── app.py              — Dash app init, tab router
├── utils.py            — SQL helpers, data fetchers, shared constants
├── pages/
│   ├── overview.py     — Overview tab layout + callbacks
│   ├── tables.py       — Tables tab layout + callbacks
│   └── settings.py     — Configure tab layout + callbacks
├── server/
│   ├── config.py       — Databricks SDK client + SQL execution
│   └── config_store.py — Delta-backed config persistence
├── app.yaml            — App runtime command + env vars
├── requirements.txt    — Python dependencies (installed by Databricks Apps)
└── setup.py            — One-time grants script (run locally, not deployed)
```

---

## Step 5 — Create the Databricks App

```bash
databricks apps create databricks-tag-governance \
  --description "Unity Catalog tag governance — browse, filter, and edit table tags" \
  --profile <your-profile>
```

Wait for provisioning to finish. This creates a service principal for the app automatically.

---

## Step 6 — Run the one-time grants setup

`setup.py` applies all Unity Catalog and warehouse grants the app's service principal needs.
Run it **as a metastore admin** from your local machine after the app is created.

**Install the dependency first (local only):**

```bash
pip install databricks-sdk
```

**Basic usage** (config table catalog only):

```bash
python setup.py \
  --app-name databricks-tag-governance \
  --profile <your-profile>
```

**With governed catalog(s)** (required to scan tables and apply tags):

```bash
python setup.py \
  --app-name databricks-tag-governance \
  --profile <your-profile> \
  --target-catalogs cat1,cat2
```

### What the script grants

| Grant | Mechanism | Purpose |
|---|---|---|
| `USE CATALOG` on config catalog | SQL | App can reach the config Delta table |
| `USE SCHEMA` on config schema | SQL | App can read/write config rows |
| `CREATE TABLE` on config schema | SQL | App creates the config table on first save |
| `MODIFY` on config schema | SQL | App upserts config rows |
| `USE CATALOG` on governed catalog(s) | SQL | App can reach governed tables |
| `APPLY TAG` on governed catalog(s) | SQL | App can set and unset UC tags |
| `USE SCHEMA` on every schema | UC REST API | App can query `information_schema` per schema |
| `SELECT + MODIFY` at catalog level | UC REST API | App reads metadata and writes tags/comments |
| `CAN_USE` on SQL Warehouse | Permissions API | App can execute SQL |

> **Why UC REST API for some grants?**
> `GRANT USE SCHEMA ON ALL SCHEMAS IN CATALOG` and `GRANT SELECT ON ALL TABLES IN CATALOG`
> are not supported by the SQL statement execution API. The script uses
> `/api/2.1/unity-catalog/permissions` instead, which applies the same privileges
> with catalog-level inheritance — no SQL editor needed.

> **If any grants fail:** The script prints the label and error for each failure.
> Re-run after fixing the issue (the script is idempotent — safe to run multiple times).

---

## Step 7 — Deploy the app

```bash
databricks apps deploy databricks-tag-governance \
  --source-code-path "/Workspace/Users/<your-email>/databricks-tag-governance" \
  --profile <your-profile>
```

Check status:

```bash
databricks apps get databricks-tag-governance --profile <your-profile>
```

When `app_status.state` is `RUNNING` the app is live. The URL is in the `url` field of the output.

---

## Step 8 — First-time configuration in the UI

Open the app URL and click the **⚙️ Configure** tab.

1. **Scanned Schemas** — Add `catalog + schema` pairs to govern. Example: `my_catalog` / `sales`.
2. **Tag Names** — Add the UC tag keys your org uses. Example: `Domain`, `Subdomain`, `DataClass`.
3. **Table Exceptions** *(optional)* — Add fully-qualified table names to exclude from all counts and the table list.
4. Click **💾 Save Configuration**.

On save the app writes config to the Delta table and reloads immediately.

---

## Step 9 — Verify

**Overview tab** — KPI cards (total catalogs, schemas, tables, fully-tagged %) and bar/pie charts for Domain, Subdomain, and DataClass tag distributions. Click **Load** to fetch data.

**Tables tab** — Filter by catalog, schema, domain, or subdomain. Search by any column. Click a row to open an inline edit form for tags and description. Click **Load** to fetch data.

---

## Redeployment after code changes

```bash
DEST="/Workspace/Users/<your-email>/databricks-tag-governance"
PROFILE="<your-profile>"

databricks workspace import-dir . "$DEST" --profile "$PROFILE" --overwrite

databricks apps deploy databricks-tag-governance \
  --source-code-path "$DEST" \
  --profile "$PROFILE"
```

`setup.py` does **not** need to be re-run after code-only changes.

---

## Adding a new governed catalog later

Add the new schema(s) in the **⚙️ Configure** tab and save. Then re-run `setup.py` with the new catalog included in `--target-catalogs` — it is safe to include already-granted catalogs:

```bash
python setup.py \
  --app-name databricks-tag-governance \
  --profile <your-profile> \
  --target-catalogs existing-cat,new-cat
```

---

## Troubleshooting

### App shows "No schemas configured" on load

Config table is empty or unreachable. Open **⚙️ Configure**, add at least one schema, and save.
If saving fails, check that `CONFIG_TABLE` in `app.yaml` points to an existing catalog and schema and that Step 6 grants were applied.

### KPI counts are all zero after loading

The SP cannot read `information_schema`. Confirm `setup.py` was run with `--target-catalogs` for the governed catalog(s).

### Tags not saving after clicking Apply Changes

The SP needs `APPLY TAG` and `MODIFY` on the table's catalog. Re-run `setup.py` with the catalog in `--target-catalogs`.

### App fails to start

Check logs by appending `/logz` to the app URL:

```
https://<your-app-url>/logz
```

Common causes:

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: dash` | `requirements.txt` not picked up — redeploy |
| `SQL_WAREHOUSE_ID not set` | Check env vars in `app.yaml` |
| Warehouse stopped | Start it in the Databricks SQL UI |
| SP missing `CAN_USE` | Re-run `setup.py` |
| Port conflict | `app.yaml` command must bind to `0.0.0.0:8000` |
