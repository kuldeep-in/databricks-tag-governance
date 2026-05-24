# Multi-Region Deployment Guide — UC Tag Governance App

## Overview

This guide covers deploying the UC Tag Governance app in a **different Databricks workspace
(Region A)** than the one where your Unity Catalog data lives **(Region B)**.

This pattern is required when Databricks Apps is not available in the region where your
data resides. The app runs as a Databricks App in Region A; all SQL — including tag reads,
tag writes, and table comments — executes against the Region B SQL warehouse and Unity
Catalog. Data never leaves Region B.

```
┌──────────────────────────┐              ┌──────────────────────────┐
│  Region A Workspace      │              │  Region B Workspace      │
│                          │   SQL API    │                          │
│  Databricks App (UI)  ───┼─────────────►  SQL Warehouse           │
│                          │◄─────────────┼─ Unity Catalog           │
│  (hosts the app only)    │  results     │  (tables, tags, metadata)│
└──────────────────────────┘              └──────────────────────────┘
```

---

## Prerequisites

- A Databricks workspace in Region A with **Databricks Apps enabled**
- A Databricks workspace in Region B with:
  - At least one running **SQL warehouse**
  - **Unity Catalog** enabled with the schemas you want to govern
- A **service principal** with access to Region B (see Permissions section)
- Databricks CLI configured for Region A (`databricks auth login`)

---

## Step 1 — Service Principal Setup in Region B

Create or reuse a service principal in your Azure / Databricks account and grant it the
following Unity Catalog privileges in Region B:

| Privilege | Scope | Purpose |
|-----------|-------|---------|
| `USE CATALOG` | Target catalog(s) | Access catalog metadata |
| `USE SCHEMA` | Target schema(s) | Access schema metadata |
| `SELECT` | Target schema(s) | Read `information_schema` views |
| `APPLY TAG` | Target catalog or schema | Set / unset tags on tables |
| `MODIFY` | Target schema(s) | Update table comments |

Grant SQL warehouse access:
```sql
GRANT CAN USE ON SQL WAREHOUSE <warehouse-id> TO <service-principal>;
```

Generate a **personal access token** (PAT) or configure OAuth M2M for the service
principal. Store the token securely — it will be injected as an environment variable.

---

## Step 2 — Update `server/config.py`

The default config uses auto-injected credentials (only available when the app and data
are in the same workspace). For cross-region deployment, switch to explicit env vars:

```python
import os
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState, StatementStatus

# Injected via app.yaml env block (see Step 3)
_HOST         = os.environ["DATABRICKS_HOST"]    # Region B workspace URL
_TOKEN        = os.environ["DATABRICKS_TOKEN"]   # Service principal PAT
WAREHOUSE_ID  = os.environ["WAREHOUSE_ID"]       # Region B SQL warehouse ID
INFO_CATALOG  = os.environ.get("INFO_CATALOG", "main")


def run_sql(stmt: str, warehouse_id: str) -> list[dict]:
    w = WorkspaceClient(host=_HOST, token=_TOKEN)
    response = w.statement_execution.execute_statement(
        statement=stmt,
        warehouse_id=warehouse_id,
        wait_timeout="50s",
    )
    status: StatementStatus = response.status
    if status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"SQL failed: {status.error}")
    result = response.result
    if not result or not result.data_array:
        return []
    cols = [c.name for c in response.manifest.schema.columns]
    return [dict(zip(cols, row)) for row in result.data_array]
```

---

## Step 3 — Update `app.yaml`

Add environment variables pointing to Region B. **Do not hard-code the token** — use
Databricks secrets or the `valueFrom` secret reference:

```yaml
command:
  - "python"
  - "-m"
  - "uvicorn"
  - "app:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "8000"

env:
  - name: DATABRICKS_HOST
    value: "https://<region-b-workspace-host>"

  - name: DATABRICKS_TOKEN
    valueFrom:
      secretScope: "<secret-scope-name>"
      secretKey:   "region-b-sp-token"

  - name: WAREHOUSE_ID
    value: "<region-b-warehouse-id>"

  - name: INFO_CATALOG
    value: "main"

  - name: CONFIG_TABLE
    value: "<catalog>.<schema>.app_config"
```

Store the token in a Databricks secret scope in Region A:
```bash
databricks secrets create-scope <scope-name> --profile <region-a-profile>
databricks secrets put-secret <scope-name> region-b-sp-token \
  --string-value "<token>" --profile <region-a-profile>
```

---

## Step 4 — Create the App in Region A

```bash
# Create the app (one time)
databricks apps create databricks-tag-governance \
  --description "UC Tag Governance - cross-region" \
  --profile <region-a-profile>

# Upload source files
databricks workspace import-dir . \
  /Workspace/Users/<user>/databricks-tag-governance \
  --exclude __pycache__ \
  --exclude .venv \
  --profile <region-a-profile>

# Deploy
databricks apps deploy databricks-tag-governance \
  --source-code-path /Workspace/Users/<user>/databricks-tag-governance \
  --profile <region-a-profile>
```

---

## Step 5 — Verify

1. Open the app URL from Region A
2. Go to **Configure** → add a schema in `catalog.schema` format (from Region B)
3. Go to **Tables** → confirm tables from Region B are listed
4. Click the edit icon on a table → update a tag → confirm it saves
5. Verify the tag is visible in Region B's Unity Catalog Explorer

---

## Network & Latency Considerations

- Traffic between the app (Region A) and the SQL warehouse (Region B) travels over the
  **cloud provider's backbone network** — reliable but adds round-trip latency per query
- This app is a governance / metadata tool with infrequent, user-triggered queries;
  latency per operation is noticeable but not a blocking concern
- To minimise latency, deploy Region A as close geographically to Region B as possible

---

## Security Notes

- The service principal token grants access to Region B data — treat it as a secret
- Use Databricks secret scopes (not plain `value:` in app.yaml) for the token
- Scope the service principal's UC privileges to only the catalogs / schemas being governed
- The app itself has no persistent storage of credentials — they are injected at runtime

---

## Updating the App

After any code change, re-upload and redeploy:

```bash
databricks workspace import-dir . \
  /Workspace/Users/<user>/databricks-tag-governance \
  --exclude __pycache__ --exclude .venv \
  --profile <region-a-profile>

databricks apps deploy databricks-tag-governance \
  --source-code-path /Workspace/Users/<user>/databricks-tag-governance \
  --profile <region-a-profile>
```
