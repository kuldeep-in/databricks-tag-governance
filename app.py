import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import plotly.express as px
import dash
from dash import Dash, html, dcc, dash_table, Input, Output, State, callback, ctx, no_update, ALL, MATCH
import dash_bootstrap_components as dbc

sys.path.insert(0, os.path.dirname(__file__))

from server.config import INFO_CATALOG, WAREHOUSE_ID, run_sql
from server.config_store import get_config, reload_config, save_config

# ── Initialize config on startup ───────────────────────────────────────────────
try:
    reload_config()
except Exception:
    pass

# ── App ────────────────────────────────────────────────────────────────────────
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    title="UC Tag Governance",
)
server = app.server

# ── Color palette ──────────────────────────────────────────────────────────────
COLORS         = ["#00C2CB", "#3B9BE8", "#26C485", "#F4A261", "#A78BFA", "#F472B6", "#34D399", "#60A5FA"]
CHART_DOMAIN   = "#00C2CB"
CHART_SUB      = "#3B9BE8"
PLOTLY_TMPL    = "plotly_dark"
CARD_STYLE     = {"background": "#122040", "border": "1px solid #1E3560", "borderRadius": "8px", "padding": "16px"}

# ── SQL helpers ────────────────────────────────────────────────────────────────
def sql(stmt: str) -> list[dict]:
    return run_sql(stmt, warehouse_id=WAREHOUSE_ID)


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
            WHERE {sf}{ef}
        """)

    def fetch_dist():
        return sql(f"""
            SELECT 'domain' AS metric, tg.tag_value AS label,
                   COUNT(DISTINCT CONCAT(t.table_catalog,'.',t.table_schema,'.',t.table_name)) AS cnt
            FROM {INFO_CATALOG}.information_schema.tables t
            JOIN {INFO_CATALOG}.information_schema.table_tags tg
              ON tg.catalog_name=t.table_catalog AND tg.schema_name=t.table_schema AND tg.table_name=t.table_name
            WHERE {sf}{ef} AND tg.tag_name='Domain' GROUP BY tg.tag_value
            UNION ALL
            SELECT 'subdomain', tg.tag_value,
                   COUNT(DISTINCT CONCAT(t.table_catalog,'.',t.table_schema,'.',t.table_name))
            FROM {INFO_CATALOG}.information_schema.tables t
            JOIN {INFO_CATALOG}.information_schema.table_tags tg
              ON tg.catalog_name=t.table_catalog AND tg.schema_name=t.table_schema AND tg.table_name=t.table_name
            WHERE {sf}{ef} AND tg.tag_name='Subdomain' GROUP BY tg.tag_value
            UNION ALL
            SELECT 'dataclass', tg.tag_value,
                   COUNT(DISTINCT CONCAT(t.table_catalog,'.',t.table_schema,'.',t.table_name))
            FROM {INFO_CATALOG}.information_schema.tables t
            JOIN {INFO_CATALOG}.information_schema.table_tags tg
              ON tg.catalog_name=t.table_catalog AND tg.schema_name=t.table_schema AND tg.table_name=t.table_name
            WHERE {sf}{ef} AND tg.tag_name='DataClass' GROUP BY tg.tag_value
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
        WHERE {sf}{ef}
        GROUP BY t.table_catalog, t.table_schema, t.table_name, t.comment
        ORDER BY t.table_catalog, t.table_schema, t.table_name
    """)


# ── Layout helpers ─────────────────────────────────────────────────────────────
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


# ── Layout ─────────────────────────────────────────────────────────────────────
app.layout = dbc.Container(
    fluid=True,
    children=[
        dcc.Store(id="store-config"),
        dcc.Store(id="store-cfg-schemas"),
        dcc.Store(id="store-cfg-tags"),
        dcc.Store(id="store-cfg-exceptions"),
        dcc.Store(id="store-table-data"),
        dcc.Store(id="store-selected-row"),
        dcc.Store(id="store-edit-result"),

        html.H3("UC Tag Governance", className="mt-3 mb-3 text-white"),

        dbc.Tabs(
            id="main-tabs",
            active_tab="tab-overview",
            children=[
                dbc.Tab(label="📊 Overview",  tab_id="tab-overview"),
                dbc.Tab(label="📋 Tables",    tab_id="tab-tables"),
                dbc.Tab(label="⚙️ Configure", tab_id="tab-settings"),
            ],
        ),

        html.Div(id="tab-content", className="mt-3"),
        html.Div(id="dummy-init", style={"display": "none"}),
    ],
    style={"minHeight": "100vh", "background": "#0d1b2e"},
)


# ── Render tab content ─────────────────────────────────────────────────────────
@app.callback(Output("tab-content", "children"), Input("main-tabs", "active_tab"))
def render_tab(tab):
    if tab == "tab-overview":
        return overview_layout()
    if tab == "tab-tables":
        return tables_layout()
    if tab == "tab-settings":
        return settings_layout()
    return html.Div()


# ══════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
def overview_layout():
    cfg = get_config()
    if cfg is None or not cfg.get("schemas"):
        return dbc.Alert("No schemas configured. Go to the ⚙️ Configure tab to add schemas.", color="info")

    schemas_list = cfg.get("schemas", [])
    catalogs     = sorted({s["catalog"] for s in schemas_list})

    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Dropdown(
                id="ov-cat", options=["All"] + catalogs, value="All",
                clearable=False, className="mb-2",
            ), width=3),
            dbc.Col(dcc.Dropdown(
                id="ov-sch", options=["All"], value="All",
                clearable=False, className="mb-2",
            ), width=3),
            dbc.Col(dbc.Button("Load", id="ov-load-btn", color="primary", size="sm"), width=2),
        ]),
        html.Div(id="ov-content"),
    ])


@app.callback(
    Output("ov-sch", "options"),
    Output("ov-sch", "value"),
    Input("ov-cat", "value"),
    prevent_initial_call=True,
)
def update_ov_schema_opts(cat):
    cfg = get_config()
    if not cfg:
        return ["All"], "All"
    schemas_list = cfg.get("schemas", [])
    cat_f = None if cat == "All" else cat
    opts = sorted({s["schema"] for s in schemas_list if not cat_f or s["catalog"] == cat_f})
    return ["All"] + opts, "All"


@app.callback(
    Output("ov-content", "children"),
    Input("ov-load-btn", "n_clicks"),
    State("ov-cat", "value"),
    State("ov-sch", "value"),
    prevent_initial_call=True,
)
def load_overview(_, cat, sch):
    cfg = get_config()
    if not cfg:
        return dbc.Alert("No config loaded.", color="warning")

    cat_f = None if cat == "All" else cat
    sch_f = None if sch == "All" else sch
    filtered = resolve_schemas(cfg, cat_f, sch_f)
    exceptions = cfg.get("exceptions", [])
    sf, ef = schema_in(filtered), exc_clause(exceptions)

    try:
        result    = fetch_overview(sf, ef)
        kpis      = result["kpis"]
        dist_rows = result["dist"]

        k          = kpis[0] if kpis else {}
        total      = int(k.get("total_tables")  or 0)
        fully      = int(k.get("fully_tagged")  or 0)
        no_dom     = int(k.get("no_domain")     or 0)
        no_sub     = int(k.get("no_subdomain")  or 0)
        tagged_pct = f"{round(fully / total * 100)}%" if total else "0%"

        by_domain    = [{"domain":     r["label"], "count": int(r["cnt"])} for r in dist_rows if r["metric"] == "domain"]
        by_subdomain = [{"subdomain":  r["label"], "count": int(r["cnt"])} for r in dist_rows if r["metric"] == "subdomain"]
        by_dataclass = [{"data_class": r["label"], "count": int(r["cnt"])} for r in dist_rows if r["metric"] == "dataclass"]

        fig_domain = px.bar(pd.DataFrame(by_domain), x="count", y="domain", orientation="h",
                            color_discrete_sequence=[CHART_DOMAIN], template=PLOTLY_TMPL) if by_domain else None
        fig_sub    = px.bar(pd.DataFrame(by_subdomain), x="count", y="subdomain", orientation="h",
                            color_discrete_sequence=[CHART_SUB], template=PLOTLY_TMPL) if by_subdomain else None
        fig_dc     = px.pie(pd.DataFrame(by_dataclass), values="count", names="data_class",
                            color_discrete_sequence=COLORS, template=PLOTLY_TMPL) if by_dataclass else None

        for fig in [fig_domain, fig_sub]:
            if fig:
                fig.update_layout(height=280, margin=dict(l=0, r=10, t=10, b=0),
                                  yaxis_title="", xaxis_title="",
                                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        if fig_dc:
            fig_dc.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0),
                                 paper_bgcolor="rgba(0,0,0,0)")

        return html.Div([
            dbc.Row([
                metric_card("Total Catalogs",    len({s["catalog"] for s in filtered})),
                metric_card("Total Schemas",     len(filtered)),
                metric_card("Total Tables",      total),
                metric_card("Fully Tagged",      fully, tagged_pct),
                metric_card("Missing Domain",    no_dom),
                metric_card("Missing Subdomain", no_sub),
            ], className="mb-3 g-2"),
            dbc.Row([
                dbc.Col([
                    html.Strong("Tables by Domain", className="text-white"),
                    dcc.Graph(figure=fig_domain, config={"displayModeBar": False}) if fig_domain
                    else html.P("No Domain tags applied yet", className="text-muted"),
                ], width=4),
                dbc.Col([
                    html.Strong("Tables by Subdomain", className="text-white"),
                    dcc.Graph(figure=fig_sub, config={"displayModeBar": False}) if fig_sub
                    else html.P("No Subdomain tags applied yet", className="text-muted"),
                ], width=4),
                dbc.Col([
                    html.Strong("DataClass Distribution", className="text-white"),
                    dcc.Graph(figure=fig_dc, config={"displayModeBar": False}) if fig_dc
                    else html.P("No DataClass tags applied yet", className="text-muted"),
                ], width=4),
            ]),
        ])
    except Exception as exc:
        return dbc.Alert(f"Error loading overview: {exc}", color="danger")


# ══════════════════════════════════════════════════════════════════════════════
# TABLES
# ══════════════════════════════════════════════════════════════════════════════
def tables_layout():
    cfg = get_config()
    if cfg is None or not cfg.get("schemas"):
        return dbc.Alert("No schemas configured. Go to the ⚙️ Configure tab to add schemas.", color="info")

    schemas_list = cfg.get("schemas", [])
    catalogs     = sorted({s["catalog"] for s in schemas_list})

    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Dropdown(
                id="tbl-cat", options=["All"] + catalogs, value="All",
                clearable=False, className="mb-2",
            ), width=3),
            dbc.Col(dcc.Dropdown(
                id="tbl-sch", options=["All"], value="All",
                clearable=False, className="mb-2",
            ), width=3),
            dbc.Col(dcc.Input(
                id="tbl-search", placeholder="Search by name, tag…",
                type="text", debounce=True,
                className="form-control mb-2",
            ), width=3),
            dbc.Col(dbc.Button("Load", id="tbl-load-btn", color="primary", size="sm"), width=1),
        ]),
        dcc.Store(id="tbl-raw-data"),
        html.Div(id="tbl-filter-row"),
        html.Div(id="tbl-table-area"),
        html.Hr(style={"borderColor": "#1E3560"}),
        html.Div(id="tbl-edit-area"),
    ])


@app.callback(
    Output("tbl-sch", "options"),
    Output("tbl-sch", "value"),
    Input("tbl-cat", "value"),
    prevent_initial_call=True,
)
def update_tbl_schema_opts(cat):
    cfg = get_config()
    if not cfg:
        return ["All"], "All"
    cat_f = None if cat == "All" else cat
    opts = sorted({s["schema"] for s in cfg.get("schemas", []) if not cat_f or s["catalog"] == cat_f})
    return ["All"] + opts, "All"


@app.callback(
    Output("tbl-raw-data", "data"),
    Output("tbl-filter-row", "children"),
    Input("tbl-load-btn", "n_clicks"),
    State("tbl-cat", "value"),
    State("tbl-sch", "value"),
    State("tbl-search", "value"),
    prevent_initial_call=True,
)
def load_tables(_, cat, sch, search):
    cfg = get_config()
    if not cfg:
        return None, dbc.Alert("No config loaded.", color="warning")

    cat_f = None if cat == "All" else cat
    sch_f = None if sch == "All" else sch
    tag_cols  = cfg.get("tag_columns", [])
    filtered  = resolve_schemas(cfg, cat_f, sch_f)
    exceptions = cfg.get("exceptions", [])
    sf, ef    = schema_in(filtered), exc_clause(exceptions)

    try:
        rows = fetch_tables(sf, ef, tag_cols)
        df   = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["catalog_name", "schema_name", "table_name", "description"])
        if "_no_tags" in df.columns:
            df.drop(columns=["_no_tags"], inplace=True)

        if search and not df.empty:
            mask = df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)
            df   = df[mask]

        domain_opts  = ["All"] + sorted(df["Domain"].dropna().unique().tolist()) if "Domain" in df.columns else ["All"]
        sub_opts     = ["All"] + sorted(df["Subdomain"].dropna().unique().tolist()) if "Subdomain" in df.columns else ["All"]

        filter_row = dbc.Row([
            dbc.Col(dcc.Dropdown(
                id="tbl-dom-filter", options=domain_opts, value="All",
                clearable=False, placeholder="Filter Domain",
            ), width=3),
            dbc.Col(dcc.Dropdown(
                id="tbl-sub-filter", options=sub_opts, value="All",
                clearable=False, placeholder="Filter Subdomain",
            ), width=3),
        ], className="mb-2") if ("Domain" in df.columns or "Subdomain" in df.columns) else html.Div()

        return df.to_dict("records"), filter_row

    except Exception as exc:
        return None, dbc.Alert(f"Error loading tables: {exc}", color="danger")


@app.callback(
    Output("tbl-table-area", "children"),
    Input("tbl-raw-data", "data"),
    Input("tbl-dom-filter", "value"),
    Input("tbl-sub-filter", "value"),
    prevent_initial_call=True,
)
def render_table(raw, dom_filter, sub_filter):
    if not raw:
        return html.Div()

    cfg = get_config() or {}
    tag_cols = cfg.get("tag_columns", [])

    df = pd.DataFrame(raw)
    if dom_filter and dom_filter != "All" and "Domain" in df.columns:
        df = df[df["Domain"] == dom_filter]
    if sub_filter and sub_filter != "All" and "Subdomain" in df.columns:
        df = df[df["Subdomain"] == sub_filter]

    base_cols = ["catalog_name", "schema_name", "table_name", "description"]
    display_cols = base_cols + [c for c in tag_cols if c in df.columns]
    df = df[[c for c in display_cols if c in df.columns]]

    columns = [{"name": c.replace("_", " ").title(), "id": c} for c in df.columns]

    return html.Div([
        html.P(f'{len(df)} table{"s" if len(df) != 1 else ""}',
               className="text-muted small"),
        dash_table.DataTable(
            id="tbl-datatable",
            data=df.to_dict("records"),
            columns=columns,
            row_selectable="single",
            selected_rows=[],
            page_size=20,
            style_table={"overflowX": "auto"},
            style_header={"backgroundColor": "#122040", "color": "#fff", "fontWeight": "bold",
                          "border": "1px solid #1E3560"},
            style_cell={"backgroundColor": "#0d1b2e", "color": "#e0e0e0",
                        "border": "1px solid #1E3560", "padding": "8px",
                        "maxWidth": "200px", "overflow": "hidden", "textOverflow": "ellipsis"},
            style_data_conditional=[
                {"if": {"state": "selected"}, "backgroundColor": "#1E3560", "border": "1px solid #00C2CB"},
            ],
        ),
    ])


@app.callback(
    Output("tbl-edit-area", "children"),
    Input("tbl-datatable", "selected_rows"),
    State("tbl-datatable", "data"),
    prevent_initial_call=True,
)
def show_edit_panel(selected_rows, table_data):
    if not selected_rows or not table_data:
        return html.Div()

    row = table_data[selected_rows[0]]
    full_name = f"{row['catalog_name']}.{row['schema_name']}.{row['table_name']}"

    cfg = get_config() or {}
    tag_cols = cfg.get("tag_columns", [])

    try:
        tag_rows = sql(f"""
            SELECT tag_name, tag_value
            FROM {INFO_CATALOG}.information_schema.table_tags
            WHERE catalog_name='{row['catalog_name']}'
              AND schema_name='{row['schema_name']}'
              AND table_name='{row['table_name']}'
        """)
        current_tags = {r["tag_name"]: r["tag_value"] for r in tag_rows}
    except Exception:
        current_tags = {}

    tag_inputs = []
    for i in range(0, len(tag_cols), 2):
        pair = tag_cols[i:i+2]
        tag_inputs.append(
            dbc.Row([
                dbc.Col([
                    dbc.Label(pair[0]),
                    dbc.Input(id={"type": "tag-input", "index": pair[0]},
                              value=current_tags.get(pair[0], ""), type="text"),
                ], width=6),
                dbc.Col([
                    dbc.Label(pair[1]) if len(pair) > 1 else html.Div(),
                    dbc.Input(id={"type": "tag-input", "index": pair[1]},
                              value=current_tags.get(pair[1], ""), type="text") if len(pair) > 1 else html.Div(),
                ], width=6),
            ], className="mb-2")
        )

    return dbc.Card(
        dbc.CardBody([
            html.H5(f"Edit: {full_name}", className="text-white mb-3"),
            dcc.Store(id="edit-row-meta", data={"row": row, "tag_cols": tag_cols, "full_name": full_name}),
            dbc.Label("Description"),
            dbc.Textarea(id="edit-desc", value=row.get("description") or "", rows=2, className="mb-3"),
            html.Strong("Tags", className="text-white") if tag_cols else html.Div(),
            *tag_inputs,
            dbc.Button("✅ Apply Changes", id="edit-submit-btn", color="success", className="mt-2"),
            html.Div(id="edit-result-msg", className="mt-2"),
        ]),
        style=CARD_STYLE,
        className="mt-3",
    )


@app.callback(
    Output("edit-result-msg", "children"),
    Input("edit-submit-btn", "n_clicks"),
    State("edit-row-meta", "data"),
    State("edit-desc", "value"),
    State({"type": "tag-input", "index": ALL}, "value"),
    State({"type": "tag-input", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def apply_edit(n_clicks, meta, desc, tag_values, tag_ids):
    if not n_clicks or not meta:
        return no_update

    row      = meta["row"]
    tag_cols = meta["tag_cols"]
    full_name = meta["full_name"]
    errors   = []

    safe_desc = (desc or "").replace("'", "\\'")
    try:
        sql(f"COMMENT ON TABLE {full_name} IS '{safe_desc}'")
    except Exception as exc:
        errors.append(f"description: {exc}")

    if tag_cols and tag_values and tag_ids:
        new_tags = {tid["index"]: val for tid, val in zip(tag_ids, tag_values)}
        desired  = {k: v for k, v in new_tags.items() if k in tag_cols and v and v.strip()}
        to_unset = [k for k in tag_cols if k not in desired]
        if desired:
            tag_str = ", ".join(f"'{k}' = '{v.replace(chr(39), chr(39)*2)}'" for k, v in desired.items())
            try:
                sql(f"ALTER TABLE {full_name} SET TAGS ({tag_str})")
            except Exception as exc:
                errors.append(f"set_tags: {exc}")
        if to_unset:
            unset_str = ", ".join(f"'{k}'" for k in to_unset)
            try:
                sql(f"ALTER TABLE {full_name} UNSET TAGS ({unset_str})")
            except Exception as exc:
                errors.append(f"unset_tags: {exc}")

    if errors:
        return dbc.Alert("; ".join(errors), color="danger")
    return dbc.Alert(f"Updated {full_name}", color="success")


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURE
# ══════════════════════════════════════════════════════════════════════════════
def settings_layout():
    cfg = get_config() or {"schemas": [], "tag_columns": [], "exceptions": []}
    return html.Div([
        dcc.Store(id="cfg-schemas-store",    data=cfg.get("schemas",     [])),
        dcc.Store(id="cfg-tags-store",       data=cfg.get("tag_columns", [])),
        dcc.Store(id="cfg-exceptions-store", data=cfg.get("exceptions",  [])),

        # Scanned Schemas
        html.H5("Scanned Schemas", className="text-white"),
        html.P("Catalog + schema pairs the app will scan for tables and tags.",
               className="text-muted small"),
        html.Div(id="cfg-schemas-list"),
        dbc.Row([
            dbc.Col(dbc.Input(id="cfg-new-cat", placeholder="catalog_name", type="text"), width=4),
            dbc.Col(dbc.Input(id="cfg-new-sch", placeholder="schema_name",  type="text"), width=4),
            dbc.Col(dbc.Button("+ Add", id="cfg-add-schema-btn", color="secondary", size="sm"), width=2),
        ], className="mt-2 mb-1"),
        html.Div(id="cfg-schema-add-msg"),

        html.Hr(style={"borderColor": "#1E3560"}),

        # Tag Names
        html.H5("Tag Names", className="text-white"),
        html.P("Tag keys that will be displayed, edited, and applied to tables.",
               className="text-muted small"),
        html.Div(id="cfg-tags-list"),
        dbc.Row([
            dbc.Col(dbc.Input(id="cfg-new-tag", placeholder="TagName", type="text"), width=4),
            dbc.Col(dbc.Button("+ Add", id="cfg-add-tag-btn", color="secondary", size="sm"), width=2),
        ], className="mt-2 mb-1"),
        html.Div(id="cfg-tag-add-msg"),

        html.Hr(style={"borderColor": "#1E3560"}),

        # Table Exceptions
        html.H5("Table Exceptions", className="text-white"),
        html.P("Tables excluded from all scans, counts, and the table list.",
               className="text-muted small"),
        html.Div(id="cfg-exceptions-list"),
        dbc.Row([
            dbc.Col(dbc.Input(id="cfg-exc-cat", placeholder="catalog",    type="text"), width=3),
            dbc.Col(dbc.Input(id="cfg-exc-sch", placeholder="schema",     type="text"), width=3),
            dbc.Col(dbc.Input(id="cfg-exc-tbl", placeholder="table_name", type="text"), width=3),
            dbc.Col(dbc.Button("+ Add", id="cfg-add-exc-btn", color="secondary", size="sm"), width=2),
        ], className="mt-2 mb-1"),
        html.Div(id="cfg-exc-add-msg"),

        html.Hr(style={"borderColor": "#1E3560"}),

        dbc.Button("💾 Save Configuration", id="cfg-save-btn", color="primary", size="lg"),
        html.Div(id="cfg-save-msg", className="mt-3"),
    ])


@app.callback(
    Output("cfg-schemas-list", "children"),
    Input("cfg-schemas-store", "data"),
)
def render_schemas_list(schemas):
    if not schemas:
        return html.P("No schemas configured.", className="text-muted small")
    return [
        dbc.Row([
            dbc.Col(html.Span(f"{s['catalog']} · {s['schema']}", className="text-white"), width=10),
            dbc.Col(dbc.Button("✕", id={"type": "rm-schema", "index": i},
                               color="danger", size="sm", className="py-0"), width=2),
        ], className="mb-1")
        for i, s in enumerate(schemas)
    ]


@app.callback(
    Output("cfg-schemas-store", "data"),
    Output("cfg-new-cat", "value"),
    Output("cfg-new-sch", "value"),
    Output("cfg-schema-add-msg", "children"),
    Input("cfg-add-schema-btn", "n_clicks"),
    Input({"type": "rm-schema", "index": ALL}, "n_clicks"),
    State("cfg-schemas-store", "data"),
    State("cfg-new-cat", "value"),
    State("cfg-new-sch", "value"),
    prevent_initial_call=True,
)
def manage_schemas(add_clicks, rm_clicks, schemas, new_cat, new_sch):
    triggered = ctx.triggered_id
    schemas   = schemas or []
    if triggered == "cfg-add-schema-btn":
        if not new_cat or not new_sch:
            return schemas, new_cat, new_sch, dbc.Alert("Both catalog and schema are required.", color="warning")
        entry = {"catalog": new_cat.strip(), "schema": new_sch.strip()}
        if entry not in schemas:
            schemas = schemas + [entry]
        return schemas, "", "", no_update
    if isinstance(triggered, dict) and triggered.get("type") == "rm-schema":
        idx = triggered["index"]
        schemas = [s for i, s in enumerate(schemas) if i != idx]
        return schemas, no_update, no_update, no_update
    return no_update, no_update, no_update, no_update


@app.callback(
    Output("cfg-tags-list", "children"),
    Input("cfg-tags-store", "data"),
)
def render_tags_list(tags):
    if not tags:
        return html.P("No tags configured.", className="text-muted small")
    return [
        dbc.Row([
            dbc.Col(dbc.Badge(t, color="info", className="me-1"), width=10),
            dbc.Col(dbc.Button("✕", id={"type": "rm-tag", "index": i},
                               color="danger", size="sm", className="py-0"), width=2),
        ], className="mb-1")
        for i, t in enumerate(tags)
    ]


@app.callback(
    Output("cfg-tags-store", "data"),
    Output("cfg-new-tag", "value"),
    Output("cfg-tag-add-msg", "children"),
    Input("cfg-add-tag-btn", "n_clicks"),
    Input({"type": "rm-tag", "index": ALL}, "n_clicks"),
    State("cfg-tags-store", "data"),
    State("cfg-new-tag", "value"),
    prevent_initial_call=True,
)
def manage_tags(add_clicks, rm_clicks, tags, new_tag):
    triggered = ctx.triggered_id
    tags = tags or []
    if triggered == "cfg-add-tag-btn":
        if not new_tag or not new_tag.strip():
            return tags, new_tag, dbc.Alert("Tag name is required.", color="warning")
        t = new_tag.strip()
        if t not in tags:
            tags = tags + [t]
        return tags, "", no_update
    if isinstance(triggered, dict) and triggered.get("type") == "rm-tag":
        idx = triggered["index"]
        tags = [t for i, t in enumerate(tags) if i != idx]
        return tags, no_update, no_update
    return no_update, no_update, no_update


@app.callback(
    Output("cfg-exceptions-list", "children"),
    Input("cfg-exceptions-store", "data"),
)
def render_exceptions_list(exceptions):
    if not exceptions:
        return html.P("No exceptions — all tables in scanned schemas are included.", className="text-muted small")
    return [
        dbc.Row([
            dbc.Col(html.Span(f"{e['catalog']}.{e['schema']}.{e['table']}", className="text-white"), width=10),
            dbc.Col(dbc.Button("✕", id={"type": "rm-exc", "index": i},
                               color="danger", size="sm", className="py-0"), width=2),
        ], className="mb-1")
        for i, e in enumerate(exceptions)
    ]


@app.callback(
    Output("cfg-exceptions-store", "data"),
    Output("cfg-exc-cat", "value"),
    Output("cfg-exc-sch", "value"),
    Output("cfg-exc-tbl", "value"),
    Output("cfg-exc-add-msg", "children"),
    Input("cfg-add-exc-btn", "n_clicks"),
    Input({"type": "rm-exc", "index": ALL}, "n_clicks"),
    State("cfg-exceptions-store", "data"),
    State("cfg-exc-cat", "value"),
    State("cfg-exc-sch", "value"),
    State("cfg-exc-tbl", "value"),
    prevent_initial_call=True,
)
def manage_exceptions(add_clicks, rm_clicks, exceptions, exc_cat, exc_sch, exc_tbl):
    triggered  = ctx.triggered_id
    exceptions = exceptions or []
    if triggered == "cfg-add-exc-btn":
        if not exc_cat or not exc_sch or not exc_tbl:
            return exceptions, exc_cat, exc_sch, exc_tbl, dbc.Alert("All three fields are required.", color="warning")
        entry = {"catalog": exc_cat.strip(), "schema": exc_sch.strip(), "table": exc_tbl.strip()}
        if entry not in exceptions:
            exceptions = exceptions + [entry]
        return exceptions, "", "", "", no_update
    if isinstance(triggered, dict) and triggered.get("type") == "rm-exc":
        idx = triggered["index"]
        exceptions = [e for i, e in enumerate(exceptions) if i != idx]
        return exceptions, no_update, no_update, no_update, no_update
    return no_update, no_update, no_update, no_update, no_update


@app.callback(
    Output("cfg-save-msg", "children"),
    Input("cfg-save-btn", "n_clicks"),
    State("cfg-schemas-store",    "data"),
    State("cfg-tags-store",       "data"),
    State("cfg-exceptions-store", "data"),
    prevent_initial_call=True,
)
def save_configuration(n_clicks, schemas, tags, exceptions):
    if not n_clicks:
        return no_update
    try:
        data = {
            "schemas":     schemas     or [],
            "tag_columns": tags        or [],
            "exceptions":  exceptions  or [],
        }
        save_config(data)
        reload_config()
        return dbc.Alert("Configuration saved successfully.", color="success")
    except Exception as exc:
        return dbc.Alert(f"Save failed: {exc}", color="danger")


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8000)
