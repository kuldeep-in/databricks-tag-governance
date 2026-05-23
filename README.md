# uc-tag-governance

A Databricks App for managing Unity Catalog table tags and metadata at scale. Browse tables across schemas, view tagging coverage, and apply or update tags and descriptions through a clean UI — without writing SQL.

---

## What it does

- **Overview dashboard** — KPI cards (total tables, fully tagged, missing Domain/Subdomain), bar charts by Domain and Subdomain, DataClass pie chart, catalog/schema filters
- **Tables browser** — searchable and filterable table list with inline tag values
- **Tag editor** — click Edit on any table to update its description and all tag fields; changes are applied as `ALTER TABLE SET TAGS` and `COMMENT ON TABLE`
- **Settings page** — configure scanned schemas, tag names, and table exceptions without touching code; auto-applies required permissions on save

---

## Architecture

```
app.yaml          ← deployment config (warehouse ID, config table path)
app.py            ← FastAPI entry point, lifespan startup loader
server/
  config.py       ← workspace auth, run_sql(), WAREHOUSE_ID from env
  config_store.py ← Delta table key-value config, in-memory cache
  routes/
    tables.py     ← /api/overview, /api/tables, /api/tags, /api/schemas
    apply.py      ← /api/apply-tags
    config.py     ← /api/config GET + PUT, auto-grant logic
setup.py          ← one-time admin setup script (run before first deploy)
frontend/
  src/            ← React + Recharts + TypeScript
  dist/           ← built output served by FastAPI
```

Config is stored in a Delta table and loaded into memory at app startup. It is only re-read when the admin saves changes via the Settings page.

---

## Step 1 — Adjust configuration

Configuration lives in two places with different purposes:

- **`app.yaml`** — deployment-level infrastructure config. Set once before deploying, changed by editing the file and redeploying. The app reads these at startup before any database connection is made.
- **Settings page (⚙)** — runtime application config. Set via the UI after the app is running. Stored in the Delta config table and loaded into memory on startup.

---

### `app.yaml` — deployment config

Edit these two values to match your environment before running `databricks apps deploy`:

```yaml
env:
  - name: SQL_WAREHOUSE_ID
    value: <your-warehouse-id>
  - name: CONFIG_TABLE
    value: <catalog>.<schema>.<table>
```

#### `SQL_WAREHOUSE_ID`

The ID of the SQL warehouse the app will use for **all** SQL execution — including reading and writing the config table itself, querying `information_schema`, and running `ALTER TABLE SET TAGS`.

**Where to find it:** Databricks UI → Compute → SQL Warehouses → select your warehouse → Connection details → HTTP path → the segment after `/sql/1.0/warehouses/` is the ID.

**Impact:**
- Without this, the app cannot start — `reload_config()` runs at boot and immediately needs a warehouse to create/read the config table
- All query performance (Overview load time, Tables load time, tag edits) is directly tied to this warehouse's size and whether it is running or needs to warm up
- A serverless warehouse is recommended to avoid cold-start delays

**When to change:** If you switch to a different warehouse (e.g. larger size for better performance, or a different warehouse in a new environment). Update `app.yaml` and redeploy — no other code changes needed.

---

#### `CONFIG_TABLE`

The fully qualified path (`catalog.schema.table`) of the Delta table where the app persists its runtime configuration (scanned schemas, tag names, exceptions).

**Example values:**

```
main.default.governance_app_config
my_catalog.admin.uc_tag_governance_config
```

**Impact:**
- The table is created automatically on first boot if it does not exist — the app runs `CREATE TABLE IF NOT EXISTS` using the `SQL_WAREHOUSE_ID` warehouse
- The schema portion of this path (`catalog.schema`) is what `setup.py` and `_apply_grants()` use to determine which grants the SP needs (`USE SCHEMA`, `CREATE TABLE`, `MODIFY`)
- If you point this to a different catalog or schema, rerun `setup.py` to apply grants for the new location
- The table stores three keys: `schemas`, `tag_columns`, `exceptions` — all managed through the Settings page, never edited directly

**When to change:** When deploying to a new environment where you want config isolated in a different catalog or schema. Update `app.yaml` and redeploy.

---

### Settings page (⚙) — runtime config

Accessible via the gear icon in the top-right of the app. Changes take effect immediately after saving — no redeploy required.

---

#### Scanned Schemas

A list of `catalog + schema` pairs the app will include in all queries.

**How to add:** In Settings → Scanned Schemas, enter a catalog name and schema name, click **+ Add**.

**Impact:**
- **Overview tab** — KPI counts (total tables, fully tagged, missing Domain/Subdomain) and all three charts reflect only the tables in these schemas
- **Tables tab** — only tables from these schemas appear in the list and are available for editing
- **Filters** — the catalog and schema dropdowns in both tabs are populated from this list
- Adding a schema with no data (empty schema) has no effect on counts
- Removing a schema immediately hides its tables from all views — it does not delete any data or tags

**Permissions required per schema** (applied automatically on save, or manually):
```sql
GRANT USE CATALOG ON CATALOG `<catalog>` TO `<sp_id>`;
GRANT APPLY TAG   ON CATALOG `<catalog>` TO `<sp_id>`;
GRANT USE SCHEMA  ON SCHEMA  `<catalog>`.`<schema>` TO `<sp_id>`;
GRANT SELECT      ON SCHEMA  `<catalog>`.`<schema>` TO `<sp_id>`;
GRANT MODIFY      ON SCHEMA  `<catalog>`.`<schema>` TO `<sp_id>`;
```

> Unity Catalog's `information_schema` only shows objects the caller has `SELECT` on. If a schema is added but its tables don't appear, the SP is missing `SELECT` on that schema.

---

#### Tag Names

The list of Unity Catalog tag keys the app will display, allow editing, and apply via `ALTER TABLE SET TAGS`.

**How to add:** In Settings → Tag Names, type a tag name and click **+ Add** (or press Enter).

**Impact:**
- **Tables tab** — the visible columns in the table grid are drawn from a fixed set of important tags (`Domain`, `Subdomain`, `DataClass`, `RetentionPeriod`); all configured tags appear in the Edit modal
- **Edit modal** — every tag in this list gets its own input field; tags with a value are SET, tags left empty are UNSET on the table
- **Overview charts** — the Domain, Subdomain, and DataClass charts are hardcoded to those three tag names regardless of this list; all other tags are only editable, not charted
- Tag names are case-sensitive and must match exactly how they are defined in your Unity Catalog tag policy
- Removing a tag from this list stops the app from displaying or editing it — it does not remove the tag from tables that already have it

**Example tag names:**
```
Domain          Subdomain       DataClass
RetentionPeriod SubObject       DataElement
Constraints     RefMasterData   BronzeT
SilverT         GoldT
```

---

#### Table Exceptions

A list of specific tables (`catalog.schema.table`) to exclude from all scans.

**How to add:** In Settings → Table Exceptions, enter catalog, schema, and table name, click **+ Add**.

**Impact:**
- **Overview tab** — excluded tables are not counted in any KPI or chart
- **Tables tab** — excluded tables do not appear in the list and cannot be edited through the app
- Useful for system or audit tables that live inside a scanned schema but should not be governed (e.g. `event_log`, `auto_profiling_results`)
- Removing an exception immediately re-includes the table in all views

---

### Configuration summary

| Setting | Where | Changed by | Requires redeploy |
|---|---|---|---|
| `SQL_WAREHOUSE_ID` | `app.yaml` | Deployer (file edit) | Yes |
| `CONFIG_TABLE` | `app.yaml` | Deployer (file edit) | Yes |
| Scanned Schemas | Settings page | Admin (UI) | No |
| Tag Names | Settings page | Admin (UI) | No |
| Table Exceptions | Settings page | Admin (UI) | No |

---

## Step 2 — Publish the app

```bash
# Create the app (first time only)
databricks apps create uc-tag-governance --profile <profile>

# Deploy
databricks apps deploy uc-tag-governance \
  --source-code-path /Workspace/Users/<your-email>/uc-tag-governance \
  --profile <profile>
```

---

## Step 3 — Prerequisites: grant permissions to the app service principal

The app runs as a Databricks service principal (SP). Before it can query Unity Catalog or write the config table, the SP needs specific permissions.

Get the SP application ID first:

```bash
databricks apps get uc-tag-governance --profile <profile>
# Note the service_principal_id, then:
databricks api get /api/2.0/preview/scim/v2/ServicePrincipals/<service_principal_id> --profile <profile>
# Use the applicationId (UUID format) in the grants below
```

---

### Option 1 — Run the setup script (recommended)

`setup.py` reads `app.yaml` automatically, resolves the SP ID, and applies all required grants in one step:

```bash
cd uc-tag-governance
python setup.py --app-name uc-tag-governance --profile <profile>
```

Output shows a grant-by-grant result. Any failures print the exact SQL to run manually.

**What it grants:**

| Resource | Permission |
|---|---|
| Config table catalog | `USE CATALOG` |
| Config table schema | `USE SCHEMA` |
| Config table schema | `CREATE TABLE` |
| Config table schema | `MODIFY` |
| SQL Warehouse | `CAN USE` |

> Run `setup.py` again any time the warehouse ID or config table path changes in `app.yaml`.

---

### Option 2 — Apply permissions manually

#### 2a — SQL Warehouse

1. Go to **Compute → SQL Warehouses**
2. Select your warehouse → **Permissions**
3. Add the app SP → set to **Can use**

#### 2b — Config table catalog and schema

Run in a SQL editor as a metastore admin (replace `<sp_id>` with the SP application ID UUID and adjust catalog/schema to match your `CONFIG_TABLE`):

```sql
GRANT USE CATALOG  ON CATALOG `<catalog>`         TO `<sp_id>`;
GRANT USE SCHEMA   ON SCHEMA  `<catalog>`.`<schema>` TO `<sp_id>`;
GRANT CREATE TABLE ON SCHEMA  `<catalog>`.`<schema>` TO `<sp_id>`;
GRANT MODIFY       ON SCHEMA  `<catalog>`.`<schema>` TO `<sp_id>`;
```

#### 2c — Target schemas (scanned tables)

After opening the app for the first time, go to **Settings (⚙)**, add your schemas, and click **Save Configuration**. The app will attempt to apply the remaining grants automatically. Any that fail are shown with copy-able SQL.

If you prefer to apply them upfront:

```sql
-- Repeat for each schema you plan to scan
GRANT USE CATALOG ON CATALOG `<catalog>`          TO `<sp_id>`;
GRANT APPLY TAG   ON CATALOG `<catalog>`          TO `<sp_id>`;
GRANT USE SCHEMA  ON SCHEMA  `<catalog>`.`<schema>` TO `<sp_id>`;
GRANT SELECT      ON SCHEMA  `<catalog>`.`<schema>` TO `<sp_id>`;
GRANT MODIFY      ON SCHEMA  `<catalog>`.`<schema>` TO `<sp_id>`;
```

---

## First use after deploy

1. Open the app URL
2. Click the **⚙ Configure** icon (top right)
3. Add the schemas you want to scan (catalog + schema pairs)
4. Add the tag names to manage (e.g. `Domain`, `Subdomain`, `DataClass`)
5. Optionally add table exceptions to exclude specific tables
6. Click **Save Configuration** — review the diff in the confirmation dialog, then confirm
7. The app reloads with your config and the Overview and Tables tabs become active

---

## Updating config after first deploy

Config is stored in the Delta table defined by `CONFIG_TABLE`. It is loaded once at startup into memory. To change scanned schemas, tags, or exceptions:

1. Open **⚙ Configure**
2. Make changes
3. Click **Save Configuration** → confirm the diff → grants are re-applied automatically

To change the warehouse ID or config table path, update `app.yaml` and redeploy.

---

## Redeploying

```bash
# After any code or app.yaml change
databricks apps deploy uc-tag-governance \
  --source-code-path /Workspace/Users/<your-email>/uc-tag-governance \
  --profile <profile>
```

Config in the Delta table survives redeployments — no need to reconfigure after a redeploy.

---

## Requirements

- Databricks workspace with Unity Catalog enabled
- Databricks CLI 0.229.0+
- A running SQL Warehouse
- Admin or metastore admin access to apply grants
- Python 3.10+ (for running `setup.py` locally)
- `databricks-sdk` installed locally (`pip install databricks-sdk`)
