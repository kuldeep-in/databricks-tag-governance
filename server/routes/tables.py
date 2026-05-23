from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Query
from server.config import run_sql, WAREHOUSE_ID, INFO_CATALOG
from server.config_store import get_config

router = APIRouter()


def _resolve_schemas(cfg: dict, catalog: str | None, schema: str | None) -> list[dict]:
    schemas = cfg["schemas"]
    if catalog and schema:
        schemas = [s for s in schemas if s["catalog"] == catalog and s["schema"] == schema]
    elif catalog:
        schemas = [s for s in schemas if s["catalog"] == catalog]
    elif schema:
        schemas = [s for s in schemas if s["schema"] == schema]
    return schemas or cfg["schemas"]


def _schema_in(schemas: list[dict]) -> str:
    names = ", ".join(f"'{s['schema']}'" for s in schemas)
    return f"t.table_schema IN ({names})"


def _exc_clause(exceptions: list[dict]) -> str:
    if not exceptions:
        return ""
    clauses = " OR ".join(
        f"(t.table_catalog='{e['catalog']}' AND t.table_schema='{e['schema']}' AND t.table_name='{e['table']}')"
        for e in exceptions
    )
    return f" AND NOT ({clauses})"


# ── Overview ─────────────────────────────────────────────────────────────────

@router.get("/overview")
def get_overview(
    catalog: str = Query(None),
    schema:  str = Query(None),
):
    cfg = get_config()
    if cfg is None or not cfg.get("schemas"):
        return {
            "total_catalogs": 0, "total_schemas": 0, "total_tables": 0,
            "fully_tagged": 0, "no_domain": 0, "no_subdomain": 0,
            "by_domain": [], "by_subdomain": [], "by_dataclass": [],
            "not_configured": True,
        }

    schemas    = _resolve_schemas(cfg, catalog, schema)
    exceptions = cfg.get("exceptions", [])
    sf         = _schema_in(schemas)
    ef         = _exc_clause(exceptions)

    total_catalogs = len({s["catalog"] for s in schemas})
    total_schemas  = len(schemas)

    def sql(stmt): return run_sql(stmt, warehouse_id=WAREHOUSE_ID)

    kpis_query = f"""
        SELECT
            COUNT(*)                                                                                           AS total_tables,
            COUNT(CASE WHEN sub.domain IS NOT NULL AND sub.subdomain IS NOT NULL AND sub.dataclass IS NOT NULL
                       THEN 1 END)                                                                             AS fully_tagged,
            COUNT(CASE WHEN sub.domain    IS NULL THEN 1 END)                                                  AS no_domain,
            COUNT(CASE WHEN sub.subdomain IS NULL THEN 1 END)                                                  AS no_subdomain
        FROM {INFO_CATALOG}.information_schema.tables t
        LEFT JOIN (
            SELECT catalog_name, schema_name, table_name,
                   MAX(CASE WHEN tag_name = 'Domain'    THEN tag_value END) AS domain,
                   MAX(CASE WHEN tag_name = 'Subdomain' THEN tag_value END) AS subdomain,
                   MAX(CASE WHEN tag_name = 'DataClass' THEN tag_value END) AS dataclass
            FROM {INFO_CATALOG}.information_schema.table_tags
            GROUP BY catalog_name, schema_name, table_name
        ) sub ON sub.catalog_name = t.table_catalog
             AND sub.schema_name  = t.table_schema
             AND sub.table_name   = t.table_name
        WHERE {sf}{ef}
    """

    dist_query = f"""
        SELECT 'domain'    AS metric, tg.tag_value AS label,
               COUNT(DISTINCT CONCAT(t.table_catalog,'.',t.table_schema,'.',t.table_name)) AS cnt
        FROM {INFO_CATALOG}.information_schema.tables t
        JOIN {INFO_CATALOG}.information_schema.table_tags tg
            ON tg.catalog_name = t.table_catalog AND tg.schema_name = t.table_schema AND tg.table_name = t.table_name
        WHERE {sf}{ef} AND tg.tag_name = 'Domain'
        GROUP BY tg.tag_value

        UNION ALL

        SELECT 'subdomain' AS metric, tg.tag_value AS label,
               COUNT(DISTINCT CONCAT(t.table_catalog,'.',t.table_schema,'.',t.table_name)) AS cnt
        FROM {INFO_CATALOG}.information_schema.tables t
        JOIN {INFO_CATALOG}.information_schema.table_tags tg
            ON tg.catalog_name = t.table_catalog AND tg.schema_name = t.table_schema AND tg.table_name = t.table_name
        WHERE {sf}{ef} AND tg.tag_name = 'Subdomain'
        GROUP BY tg.tag_value

        UNION ALL

        SELECT 'dataclass' AS metric, tg.tag_value AS label,
               COUNT(DISTINCT CONCAT(t.table_catalog,'.',t.table_schema,'.',t.table_name)) AS cnt
        FROM {INFO_CATALOG}.information_schema.tables t
        JOIN {INFO_CATALOG}.information_schema.table_tags tg
            ON tg.catalog_name = t.table_catalog AND tg.schema_name = t.table_schema AND tg.table_name = t.table_name
        WHERE {sf}{ef} AND tg.tag_name = 'DataClass'
        GROUP BY tg.tag_value
        ORDER BY metric, cnt DESC
    """

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_kpis = pool.submit(sql, kpis_query)
        f_dist = pool.submit(sql, dist_query)
        kpis      = f_kpis.result()
        dist_rows = f_dist.result()

    k            = kpis[0] if kpis else {}
    by_domain    = [{"domain":     r["label"], "count": int(r["cnt"])} for r in dist_rows if r["metric"] == "domain"]
    by_subdomain = [{"subdomain":  r["label"], "count": int(r["cnt"])} for r in dist_rows if r["metric"] == "subdomain"]
    by_dataclass = [{"data_class": r["label"], "count": int(r["cnt"])} for r in dist_rows if r["metric"] == "dataclass"]

    return {
        "total_catalogs": total_catalogs,
        "total_schemas":  total_schemas,
        "total_tables":   int(k.get("total_tables")   or 0),
        "fully_tagged":   int(k.get("fully_tagged")   or 0),
        "no_domain":      int(k.get("no_domain")      or 0),
        "no_subdomain":   int(k.get("no_subdomain")   or 0),
        "by_domain":       by_domain,
        "by_subdomain":    by_subdomain,
        "by_dataclass":    by_dataclass,
    }


# ── Tables list ───────────────────────────────────────────────────────────────

@router.get("/tables")
def get_tables(
    catalog: str = Query(None),
    schema:  str = Query(None),
):
    cfg = get_config()
    if cfg is None or not cfg.get("schemas"):
        return []

    schemas    = _resolve_schemas(cfg, catalog, schema)
    exceptions = cfg.get("exceptions", [])
    sf         = _schema_in(schemas)
    ef         = _exc_clause(exceptions)
    tag_cols   = cfg["tag_columns"]

    tag_cases = ",\n".join(
        f"    MAX(CASE WHEN tg.tag_name = '{col}' THEN tg.tag_value END) AS `{col}`"
        for col in tag_cols
    )

    rows = run_sql(f"""
        SELECT t.table_catalog AS catalog_name,
               t.table_schema  AS schema_name,
               t.table_name,
               t.comment       AS description,
               {tag_cases}
        FROM {INFO_CATALOG}.information_schema.tables t
        LEFT JOIN {INFO_CATALOG}.information_schema.table_tags tg
            ON tg.catalog_name = t.table_catalog AND tg.schema_name = t.table_schema AND tg.table_name = t.table_name
        WHERE {sf}{ef}
        GROUP BY t.table_catalog, t.table_schema, t.table_name, t.comment
        ORDER BY t.table_catalog, t.table_schema, t.table_name
    """, warehouse_id=WAREHOUSE_ID)
    return rows


# ── Tags for single table ─────────────────────────────────────────────────────

@router.get("/tags/{catalog}/{schema}/{table}")
def get_tags(catalog: str, schema: str, table: str):
    cfg = get_config()
    if cfg is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="App not configured. Please set up via the Settings page.")

    rows = run_sql(f"""
        SELECT tag_name, tag_value
        FROM {INFO_CATALOG}.information_schema.table_tags
        WHERE catalog_name = '{catalog}' AND schema_name = '{schema}' AND table_name = '{table}'
    """, warehouse_id=WAREHOUSE_ID)
    tags = {r["tag_name"]: r["tag_value"] for r in rows}

    desc_rows = run_sql(f"""
        SELECT comment FROM {INFO_CATALOG}.information_schema.tables
        WHERE table_catalog = '{catalog}' AND table_schema = '{schema}' AND table_name = '{table}'
    """, warehouse_id=WAREHOUSE_ID)
    description = desc_rows[0]["comment"] if desc_rows else ""
    return {"tags": tags, "description": description or ""}


# ── Schema list (always from live config) ─────────────────────────────────────

@router.get("/schemas")
def get_schemas():
    cfg = get_config()
    if cfg is None:
        return []
    return cfg.get("schemas", [])
