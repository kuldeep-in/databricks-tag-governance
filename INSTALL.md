# Installation Guide — UC Tag Governance App

A step-by-step guide to deploying the Unity Catalog Tag Governance Databricks App.

> **No build step required.** The app is built entirely in Python (Streamlit + FastAPI backend logic).
> No Node.js, npm, or frontend compilation needed.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Databricks CLI ≥ 0.229.0 | `pip install databricks-cli` or download from [docs](https://docs.databricks.com/dev-tools/cli/install.html) |
| Python ≥ 3.11 | Required to run `setup.py` locally |
| Workspace admin role | Needed to create the app and run grants |
| Unity Catalog metastore | Tables must be in UC-managed catalogs |
| SQL Warehouse | Used for all SQL queries at runtime |

---

## Step 1 — Authenticate the Databricks CLI

```bash
databricks auth login --host https://<your-workspace>.azuredatabricks.net --profile <your-profile>
```

Verify authentication:

```bash
databricks auth profiles
```

---

## Step 2 — Get the source code

Clone or copy the repository contents to a local directory:

```bash
git clone <repo-url>
cd databricks-tag-governance
```

---

## Step 3 — Configure `app.yaml`

Open `app.yaml` and fill in the three placeholder values:

```yaml
command:
  - "streamlit"
  - "run"
  - "app.py"
  - "--server.port=8000"
  - "--server.address=0.0.0.0"
  - "--server.headless=true"

env:
  - name: SQL_WAREHOUSE_ID
    value: <your-warehouse-id>        # ← paste your warehouse ID here

  - name: CONFIG_TABLE
    value: <your-catalog>.default.uc_tag_governance_config
    # ↑ Delta table where the app stores its own config.
    #   The catalog and schema must already exist.
    #   The table will be created automatically on first save.

  - name: INFO_CATALOG
    value: <your-catalog>
    # ↑ The catalog whose information_schema the app queries.
    #   Often the same catalog as CONFIG_TABLE, but can differ.
```

**Finding your Warehouse ID:**
Go to SQL Warehouses in the Databricks UI → click your warehouse → copy the ID from the URL or the Connection Details tab.

---

## Step 4 — Upload source files to Databricks Workspace

Choose a destination path in your workspace:

```
/Workspace/Users/<your-email>/uc-tag-governance/
```

Create the directory structure and upload all files:

```bash
DEST="/Workspace/Users/<your-email>/uc-tag-governance"
PROFILE="<your-profile>"

# Create directories
databricks workspace mkdirs "$DEST/server/routes" --profile $PROFILE

# Upload root files
for f in app.py app.yaml requirements.txt setup.py; do
  databricks workspace import "$DEST/$f" --file "$f" --format RAW --overwrite --profile $PROFILE
done

# Upload server modules
for f in server/__init__.py server/config.py server/config_store.py server/routes/__init__.py; do
  databricks workspace import "$DEST/$f" --file "$f" --format RAW --overwrite --profile $PROFILE
done
```

> **Note:** There is no frontend build step. The `frontend/` directory is no longer required.

---

## Step 5 — Create the Databricks App

```bash
databricks apps create uc-tag-governance \
  --description "Unity Catalog tag governance — browse, filter, and edit table tags" \
  --profile <your-profile>
```

Wait for the app to be created (this provisions a service principal automatically).

---

## Step 6 — Run the one-time grants setup

`setup.py` applies all Unity Catalog grants the app's service principal needs to read `information_schema` and apply tags. Run it as a metastore admin from your local machine.

**Basic usage (config table catalog only):**

```bash
python setup.py \
  --app-name uc-tag-governance \
  --profile <your-profile>
```

**If the governed catalog(s) differ from the config catalog:**

```bash
python setup.py \
  --app-name uc-tag-governance \
  --profile <your-profile> \
  --target-catalogs cat1,cat2
```

The `--target-catalogs` flag grants the SP catalog-level access (`USE SCHEMA ON ALL SCHEMAS IN CATALOG`, `SELECT ON ALL TABLES`, `MODIFY ON ALL TABLES`, `APPLY TAG`) so that every schema in those catalogs is immediately accessible without per-schema grants.

**What the script grants:**

| Grant | Purpose |
|---|---|
| `USE CATALOG` on config catalog | App can reach the config table |
| `USE SCHEMA` on config schema | App can read/write the config table |
| `CREATE TABLE` on config schema | App creates the config table on first save |
| `MODIFY` on config schema | App upserts config rows |
| `USE CATALOG` on governed catalog(s) | App can reach the catalog |
| `APPLY TAG` on governed catalog(s) | App can set and unset UC tags |
| `USE SCHEMA ON ALL SCHEMAS` | App can query `information_schema` in every schema |
| `SELECT ON ALL TABLES` | App can read table metadata |
| `MODIFY ON ALL TABLES` | App can write tags and comments |
| `CAN_USE` on SQL Warehouse | App can execute SQL |

> **Note:** If any grants fail (printed with ✗), the script shows the exact SQL statements to run manually. Paste them into a SQL editor as a metastore admin.

---

## Step 7 — Deploy the app

```bash
databricks apps deploy uc-tag-governance \
  --source-code-path "/Workspace/Users/<your-email>/uc-tag-governance" \
  --profile <your-profile>
```

Watch the deployment status:

```bash
databricks apps get uc-tag-governance --profile <your-profile>
```

When the `state` shows `RUNNING`, the app is live. The URL is shown in the output under `url`.

---

## Step 8 — First-time configuration via the UI

Open the app URL in a browser and click the **⚙️ Configure** tab (top of the page).

1. **Scanned Schemas** — Add each `catalog + schema` pair you want the app to govern. Example: `my_catalog` / `my_schema`.
2. **Tag Names** — Add the tag keys your organization uses. Example: `Domain`, `Subdomain`, `DataClass`, `RetentionPeriod`.
3. **Table Exceptions** *(optional)* — Add fully-qualified table names to exclude from all counts and the table list.
4. Click **💾 Save Configuration**.

On save, the app:
- Writes the config to the Delta table (`CONFIG_TABLE`)
- Auto-applies catalog-level grants for any newly added catalogs using your logged-in OAuth token (requires MANAGE GRANTS privilege)
- Reloads the in-memory config so changes are reflected immediately

---

## Step 9 — Verify

Navigate to the **📊 Overview** tab. You should see:

- KPI cards showing total catalogs, schemas, tables, and tagging coverage
- Bar charts for tables by Domain and Subdomain
- DataClass pie chart (populates once DataClass tags are applied)

Navigate to the **📋 Tables** tab to browse tables. Click any row to expand an inline edit form to apply tags and update descriptions.

---

## Redeployment after code changes

When you update source files (no build step needed):

```bash
DEST="/Workspace/Users/<your-email>/uc-tag-governance"
PROFILE="<your-profile>"

# Re-upload changed files
databricks workspace import "$DEST/app.py" --file app.py --format RAW --overwrite --profile $PROFILE

# Redeploy
databricks apps deploy uc-tag-governance \
  --source-code-path "$DEST" \
  --profile $PROFILE
```

---

## Adding a new governed catalog later

If you add a new catalog in the **Configure** tab, the app automatically runs catalog-level grants using your logged-in token at save time. This covers all schemas in the catalog immediately.

If automatic grants fail (visible as an error after saving), run manually as a metastore admin:

```sql
GRANT USE CATALOG   ON CATALOG `<new-catalog>` TO `<app-sp-uuid>`;
GRANT APPLY TAG     ON CATALOG `<new-catalog>` TO `<app-sp-uuid>`;
GRANT USE SCHEMA    ON ALL SCHEMAS IN CATALOG `<new-catalog>` TO `<app-sp-uuid>`;
GRANT SELECT        ON ALL TABLES  IN CATALOG `<new-catalog>` TO `<app-sp-uuid>`;
GRANT MODIFY        ON ALL TABLES  IN CATALOG `<new-catalog>` TO `<app-sp-uuid>`;
```

The SP UUID can be found by running:

```bash
python setup.py --app-name uc-tag-governance --profile <your-profile>
```

---

## Troubleshooting

### App shows "No schemas configured" on load

The config table is empty or unreachable. Open the **Configure** tab, add at least one schema, and save. If saving fails, check that `CONFIG_TABLE` in `app.yaml` points to an existing catalog and schema.

### KPI counts are all zero

The app's service principal cannot see tables in `information_schema`. Ensure Step 6 (`setup.py`) was run for the governed catalog(s), or run the grants manually (see above).

### App fails to start

Check logs by appending `/logz` to the app URL:

```
https://<your-app-url>/logz
```

Common causes:
- `SQL_WAREHOUSE_ID` or `CONFIG_TABLE` env vars not set in `app.yaml`
- SQL Warehouse is stopped — start it in the Databricks UI
- SP does not have `CAN_USE` on the warehouse — run `setup.py` or grant manually

### Tags not persisting after clicking Apply Changes

The SP needs `APPLY TAG` and `MODIFY` on the target table's catalog. Confirm the governed catalog was included in `--target-catalogs` when running `setup.py`.
