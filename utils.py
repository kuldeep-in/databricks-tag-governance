from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import dash_bootstrap_components as dbc
from dash import html

from server.config import INFO_CATALOG, WAREHOUSE_ID, run_sql

# ── Color palette ──────────────────────────────────────────────────────────────
COLORS       = ["#00C2CB", "#3B9BE8", "#26C485", "#F4A261", "#A78BFA", "#F472B6", "#34D399", "#60A5FA"]
CHART_DOMAIN = "#00C2CB"
CHART_SUB    = "#3B9BE8"
PLOTLY_TMPL  = "plotly_dark"
CARD_STYLE   = {"background": "#122040", "border": "1px solid #1E3560", "borderRadius": "8px", "padding": "16px"}


# ── SQL ────────────────────────────────────────────────────────────────────────
def sql(stmt: str) -> list[dict]:
    return run_sql(stmt, warehouse_id=WAREHOUSE_ID)


# ── Schema / filter helpers ────────────────────────────────────────────────────
def schema_in(schemas: list[dict]) -> str:
    names = ", ".join(f"'{s['schema']}'" for s in schemas)
    return f"t.table_schema IN ({names})"


def exc_clause(exceptions: list[dict]) -> str:
    if not exceptions:
        return ""
    clauses = " OR ".join(
        f"(t.table_catalog='{e['catalog']}' AND t.table_schema='{e['schema']}' AND t.table_name='{e['table']}')"
        for e in exceptions
    )
    return f" AND NOT ({clauses})"


def resolve_schemas(cfg: dict, catalog, schema) -> list[dict]:
    schemas = cfg.get("schemas", [])
    if catalog and schema:
        schemas = [s for s in schemas if s["catalog"] == catalog and s["schema"] == schema]
    elif catalog:
        schemas = [s for s in schemas if s["catalog"] == catalog]
    elif schema:
        schemas = [s for s in schemas if s["schema"] == schema]
    return schemas or cfg.get("schemas", [])


# ── Data fetchers ──────────────────────────────────────────────────────────────
_INTERNAL_TABLE_FILTER = " AND t.table_name NOT LIKE 'event_log_%'"


def fetch_overview(sf: str, ef: str) -> dict:
    def fetch_kpis():
        return sql(f"""
            SELECT
              COUNT(*) AS total_tables,
              COUNT(CASE WHEN sub.domain IS NOT NULL
                          AND sub.subdomain IS NOT NULL
                          AND sub.dataclass IS NOT NULL THEN 1 END) AS fully_tagged,
              COUNT(CASE WHEN sub.domain    IS NULL THEN 1 END) AS no_domain,
              COUNT(CASE WHEN sub.subdomain IS NULL THEN 1 END) AS no_subdomain
            FROM {INFO_CATALOG}.information_schema.tables t
            LEFT JOIN (
              SELECT catalog_name, schema_name, table_name,
                     MAX(CASE WHEN tag_name='Domain'    THEN tag_value END) AS domain,
                     MAX(CASE WHEN tag_name='Subdomain' THEN tag_value END) AS subdomain,
                     MAX(CASE WHEN tag_name='DataClass' THEN tag_value END) AS dataclass
              FROM {INFO_CATALOG}.information_schema.table_tags
              GROUP BY catalog_name, schema_name, table_name
            ) sub ON sub.catalog_name=t.table_catalog
                 AND sub.schema_name=t.table_schema
                 AND sub.table_name=t.table_name
            WHERE {sf}{ef}{_INTERNAL_TABLE_FILTER}
        """)

    def fetch_dist():
        return sql(f"""
            SELECT 'domain' AS metric, tg.tag_value AS label,
                   COUNT(DISTINCT CONCAT(t.table_catalog,'.',t.table_schema,'.',t.table_name)) AS cnt
            FROM {INFO_CATALOG}.information_schema.tables t
            JOIN {INFO_CATALOG}.information_schema.table_tags tg
              ON tg.catalog_name=t.table_catalog AND tg.schema_name=t.table_schema AND tg.table_name=t.table_name
            WHERE {sf}{ef}{_INTERNAL_TABLE_FILTER} AND tg.tag_name='Domain' GROUP BY tg.tag_value
            UNION ALL
            SELECT 'subdomain', tg.tag_value,
                   COUNT(DISTINCT CONCAT(t.table_catalog,'.',t.table_schema,'.',t.table_name))
            FROM {INFO_CATALOG}.information_schema.tables t
            JOIN {INFO_CATALOG}.information_schema.table_tags tg
              ON tg.catalog_name=t.table_catalog AND tg.schema_name=t.table_schema AND tg.table_name=t.table_name
            WHERE {sf}{ef}{_INTERNAL_TABLE_FILTER} AND tg.tag_name='Subdomain' GROUP BY tg.tag_value
            UNION ALL
            SELECT 'dataclass', tg.tag_value,
                   COUNT(DISTINCT CONCAT(t.table_catalog,'.',t.table_schema,'.',t.table_name))
            FROM {INFO_CATALOG}.information_schema.tables t
            JOIN {INFO_CATALOG}.information_schema.table_tags tg
              ON tg.catalog_name=t.table_catalog AND tg.schema_name=t.table_schema AND tg.table_name=t.table_name
            WHERE {sf}{ef}{_INTERNAL_TABLE_FILTER} AND tg.tag_name='DataClass' GROUP BY tg.tag_value
            ORDER BY metric, cnt DESC
        """)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_kpis = pool.submit(fetch_kpis)
        f_dist = pool.submit(fetch_dist)
        return {"kpis": f_kpis.result(), "dist": f_dist.result()}


def fetch_tables(sf: str, ef: str, tag_cols: list[str]) -> list[dict]:
    tag_cases = (
        ",\n".join(f"MAX(CASE WHEN tg.tag_name='{c}' THEN tg.tag_value END) AS `{c}`" for c in tag_cols)
        if tag_cols else "NULL AS _no_tags"
    )
    return sql(f"""
        SELECT t.table_catalog AS catalog_name,
               t.table_schema  AS schema_name,
               t.table_name,
               t.comment       AS description,
               {tag_cases}
        FROM {INFO_CATALOG}.information_schema.tables t
        LEFT JOIN {INFO_CATALOG}.information_schema.table_tags tg
          ON tg.catalog_name=t.table_catalog AND tg.schema_name=t.table_schema AND tg.table_name=t.table_name
        WHERE {sf}{ef}{_INTERNAL_TABLE_FILTER}
        GROUP BY t.table_catalog, t.table_schema, t.table_name, t.comment
        ORDER BY t.table_catalog, t.table_schema, t.table_name
    """)


# ── Shared component ───────────────────────────────────────────────────────────
def metric_card(label: str, value, delta: str = ""):
    return dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.P(label, className="text-muted mb-1", style={"fontSize": "0.8rem"}),
                html.H4(str(value), className="mb-0 text-white"),
                html.Small(delta, className="text-info") if delta else html.Span(),
            ]),
            style=CARD_STYLE,
        ),
        className="px-1",
    )
