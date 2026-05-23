import pandas as pd
import dash_bootstrap_components as dbc
from dash import html, dcc, dash_table, Input, Output, State, ctx, no_update, ALL

from server.config import INFO_CATALOG
from server.config_store import get_config
from utils import (
    CARD_STYLE, sql,
    fetch_tables, resolve_schemas, schema_in, exc_clause,
)


def layout():
    cfg = get_config()
    if cfg is None or not cfg.get("schemas"):
        return dbc.Alert("No schemas configured. Go to the ⚙️ Configure tab to add schemas.", color="info")

    catalogs = sorted({s["catalog"] for s in cfg["schemas"]})
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
                type="text", debounce=True, className="form-control mb-2",
            ), width=3),
            dbc.Col(dbc.Button("Load", id="tbl-load-btn", color="primary", size="sm"), width=1),
        ]),
        dcc.Store(id="tbl-raw-data"),
        html.Div(id="tbl-filter-row"),
        html.Div(id="tbl-table-area"),
        html.Hr(style={"borderColor": "#1E3560"}),
        html.Div(id="tbl-edit-area"),
    ])


def register_callbacks(app):

    @app.callback(
        Output("tbl-sch", "options"),
        Output("tbl-sch", "value"),
        Input("tbl-cat", "value"),
        prevent_initial_call=True,
    )
    def update_schema_opts(cat):
        cfg = get_config()
        if not cfg:
            return ["All"], "All"
        cat_f = None if cat == "All" else cat
        opts = sorted({s["schema"] for s in cfg["schemas"] if not cat_f or s["catalog"] == cat_f})
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

        cat_f      = None if cat == "All" else cat
        sch_f      = None if sch == "All" else sch
        tag_cols   = cfg.get("tag_columns", [])
        filtered   = resolve_schemas(cfg, cat_f, sch_f)
        exceptions = cfg.get("exceptions", [])
        sf, ef     = schema_in(filtered), exc_clause(exceptions)

        try:
            rows = fetch_tables(sf, ef, tag_cols)
            df   = pd.DataFrame(rows) if rows else pd.DataFrame(
                columns=["catalog_name", "schema_name", "table_name", "description"])
            if "_no_tags" in df.columns:
                df.drop(columns=["_no_tags"], inplace=True)

            if search and not df.empty:
                mask = df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)
                df   = df[mask]

            domain_opts = ["All"] + sorted(df["Domain"].dropna().unique().tolist()) if "Domain" in df.columns else ["All"]
            sub_opts    = ["All"] + sorted(df["Subdomain"].dropna().unique().tolist()) if "Subdomain" in df.columns else ["All"]

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

        cfg      = get_config() or {}
        tag_cols = cfg.get("tag_columns", [])
        df       = pd.DataFrame(raw)

        if dom_filter and dom_filter != "All" and "Domain" in df.columns:
            df = df[df["Domain"] == dom_filter]
        if sub_filter and sub_filter != "All" and "Subdomain" in df.columns:
            df = df[df["Subdomain"] == sub_filter]

        base_cols    = ["catalog_name", "schema_name", "table_name", "description"]
        display_cols = base_cols + [c for c in tag_cols if c in df.columns]
        df           = df[[c for c in display_cols if c in df.columns]]
        columns      = [{"name": c.replace("_", " ").title(), "id": c} for c in df.columns]

        return html.Div([
            html.P(f'{len(df)} table{"s" if len(df) != 1 else ""}', className="text-muted small"),
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

        row       = table_data[selected_rows[0]]
        full_name = f"{row['catalog_name']}.{row['schema_name']}.{row['table_name']}"
        cfg       = get_config() or {}
        tag_cols  = cfg.get("tag_columns", [])

        try:
            tag_rows     = sql(f"""
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

        full_name = meta["full_name"]
        tag_cols  = meta["tag_cols"]
        errors    = []

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
