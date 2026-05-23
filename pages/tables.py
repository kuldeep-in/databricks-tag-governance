import pandas as pd
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, ctx, no_update, ALL

from server.config import INFO_CATALOG
from server.config_store import get_config
from utils import (
    CARD_STYLE, sql,
    fetch_tables, resolve_schemas, schema_in, exc_clause,
)

_TH = {
    "backgroundColor": "#122040", "color": "#9fb3cc",
    "fontWeight": "600", "fontSize": "0.78rem", "textAlign": "left",
    "padding": "8px 12px", "border": "1px solid #1E3560",
    "whiteSpace": "nowrap", "letterSpacing": "0.03em",
}
_TD = {
    "backgroundColor": "#0d1b2e", "color": "#d4e0ef",
    "fontSize": "0.82rem", "textAlign": "left",
    "padding": "7px 12px", "border": "1px solid #1E3560",
    "maxWidth": "240px", "overflow": "hidden",
    "textOverflow": "ellipsis", "whiteSpace": "nowrap",
}
_TD_ACTION = {**_TD, "textAlign": "center", "width": "72px", "maxWidth": "72px"}


def layout():
    cfg         = get_config() or {}
    catalogs    = sorted({s["catalog"] for s in cfg.get("schemas", [])})
    all_schemas = sorted({s["schema"]  for s in cfg.get("schemas", [])})
    return html.Div([
        dcc.Interval(id="tbl-auto-load", interval=300, max_intervals=1),
        dcc.Store(id="tbl-refresh-signal", data=0),
        dcc.Store(id="edit-row-meta"),

        # ── Edit modal ──────────────────────────────────────────────────────────
        dbc.Modal(
            id="tbl-edit-modal",
            is_open=False,
            size="lg",
            backdrop="static",
            children=[
                dbc.ModalHeader(
                    dbc.ModalTitle(id="tbl-edit-modal-title"),
                    style={"backgroundColor": "#122040", "borderBottom": "1px solid #1E3560"},
                ),
                dbc.ModalBody(
                    id="tbl-edit-modal-body",
                    style={"backgroundColor": "#0d1b2e"},
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button("Save Changes", id="edit-submit-btn", color="success", size="sm"),
                        dbc.Button("Cancel", id="tbl-edit-cancel-btn",
                                   color="secondary", outline=True, size="sm", className="ms-2"),
                    ],
                    style={"backgroundColor": "#122040", "borderTop": "1px solid #1E3560"},
                ),
            ],
        ),

        # ── Filters ─────────────────────────────────────────────────────────────
        dbc.Row([
            dbc.Col([
                html.Label("Catalog", className="text-muted small mb-1"),
                dcc.Dropdown(id="tbl-cat", options=["All"] + catalogs,
                             value="All", clearable=False),
            ], width=2),
            dbc.Col([
                html.Label("Schema", className="text-muted small mb-1"),
                dcc.Dropdown(id="tbl-sch", options=["All"] + all_schemas,
                             value="All", clearable=False),
            ], width=2),
            dbc.Col([
                html.Label("Domain", className="text-muted small mb-1"),
                dcc.Dropdown(id="tbl-dom-filter", options=["All", "<null>"],
                             value="All", clearable=False),
            ], width=2),
            dbc.Col([
                html.Label("Subdomain", className="text-muted small mb-1"),
                dcc.Dropdown(id="tbl-sub-filter", options=["All", "<null>"],
                             value="All", clearable=False),
            ], width=2),
            dbc.Col([
                html.Label("Search", className="text-muted small mb-1"),
                dcc.Input(id="tbl-search", placeholder="Search by name, tag…",
                          type="text", debounce=True, className="form-control"),
            ], width=2),
            dbc.Col(
                dbc.Button("🔄 Refresh", id="tbl-load-btn", color="primary", size="sm"),
                width="auto", className="ms-auto align-self-end pb-1",
            ),
        ], className="mb-3 align-items-end"),

        dcc.Store(id="tbl-raw-data"),
        html.Div(id="tbl-table-area"),
    ])


def _build_table(df: pd.DataFrame, tag_cols: list[str]) -> html.Div:
    base_cols    = ["catalog_name", "schema_name", "table_name", "description"]
    display_cols = base_cols + [c for c in tag_cols if c in df.columns]
    display_cols = [c for c in display_cols if c in df.columns]

    header = html.Thead(html.Tr(
        [html.Th(c.replace("_", " ").title(), style=_TH) for c in display_cols]
        + [html.Th("", style={**_TH, "textAlign": "center", "width": "72px"})],
    ))

    rows = []
    for i, row in enumerate(df.to_dict("records")):
        cells = [html.Td(str(row.get(c) or ""), style=_TD) for c in display_cols]
        cells.append(html.Td(
            dbc.Button(html.I(className="bi bi-pencil-square"),
                       id={"type": "tbl-edit-btn", "index": i},
                       size="sm", color="primary", outline=True,
                       style={"padding": "2px 7px", "borderRadius": "4px", "lineHeight": "1"}),
            style=_TD_ACTION,
        ))
        rows.append(html.Tr(cells))

    return html.Div(
        html.Table(
            [header, html.Tbody(rows)],
            style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.82rem"},
        ),
        style={"overflowX": "auto", "overflowY": "auto", "maxHeight": "60vh",
               "border": "1px solid #1E3560", "borderRadius": "6px"},
    )


def register_callbacks(app):

    @app.callback(
        Output("tbl-cat", "options"),
        Output("tbl-sch", "options"),
        Output("tbl-sch", "value"),
        Input("tbl-cat", "value"),
        Input("cfg-version", "data"),
        prevent_initial_call=True,
    )
    def update_filter_opts(cat, _version):
        cfg   = get_config() or {}
        schs  = cfg.get("schemas", [])
        cats  = sorted({s["catalog"] for s in schs})
        cat_f = None if not cat or cat == "All" else cat
        sch_l = sorted({s["schema"] for s in schs if not cat_f or s["catalog"] == cat_f})
        return ["All"] + cats, ["All"] + sch_l, "All"

    @app.callback(
        Output("tbl-raw-data",      "data"),
        Output("tbl-dom-filter",    "options"),
        Output("tbl-sub-filter",    "options"),
        Input("tbl-load-btn",       "n_clicks"),
        Input("tbl-auto-load",      "n_intervals"),
        Input("cfg-version",        "data"),
        Input("tbl-refresh-signal", "data"),
        Input("tbl-cat",            "value"),
        Input("tbl-sch",            "value"),
        State("tbl-search", "value"),
        prevent_initial_call=True,
    )
    def load_tables(_, _intervals, _version, _refresh, cat, sch, search):
        _base = ["All", "<null>"]
        cfg   = get_config()
        if not cfg or not cfg.get("schemas"):
            return None, _base, _base

        cat_f      = None if cat == "All" else cat
        sch_f      = None if sch == "All" else sch
        tag_cols   = cfg.get("tag_columns", [])
        filtered   = resolve_schemas(cfg, cat_f, sch_f)
        sf         = schema_in(filtered)
        ef         = exc_clause(cfg.get("exceptions", []))

        try:
            rows = fetch_tables(sf, ef, tag_cols)
            df   = pd.DataFrame(rows) if rows else pd.DataFrame(
                columns=["catalog_name", "schema_name", "table_name", "description"])
            if "_no_tags" in df.columns:
                df.drop(columns=["_no_tags"], inplace=True)

            if search and not df.empty:
                mask = df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)
                df   = df[mask]

            dom_vals = sorted(df["Domain"].dropna().unique().tolist())    if "Domain"    in df.columns else []
            sub_vals = sorted(df["Subdomain"].dropna().unique().tolist()) if "Subdomain" in df.columns else []
            return df.to_dict("records"), _base + [v for v in dom_vals if v], _base + [v for v in sub_vals if v]

        except Exception:
            return None, _base, _base

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

        if dom_filter == "<null>" and "Domain" in df.columns:
            df = df[df["Domain"].isna() | (df["Domain"] == "")]
        elif dom_filter and dom_filter != "All" and "Domain" in df.columns:
            df = df[df["Domain"] == dom_filter]

        if sub_filter == "<null>" and "Subdomain" in df.columns:
            df = df[df["Subdomain"].isna() | (df["Subdomain"] == "")]
        elif sub_filter and sub_filter != "All" and "Subdomain" in df.columns:
            df = df[df["Subdomain"] == sub_filter]

        df = df.reset_index(drop=True)
        return html.Div([
            html.P(f'{len(df)} table{"s" if len(df) != 1 else ""}',
                   className="text-muted small mb-2"),
            _build_table(df, tag_cols),
        ])

    # ── Open edit modal ──────────────────────────────────────────────────────────

    @app.callback(
        Output("tbl-edit-modal",       "is_open"),
        Output("tbl-edit-modal-title", "children"),
        Output("tbl-edit-modal-body",  "children"),
        Output("edit-row-meta",        "data"),
        Input({"type": "tbl-edit-btn", "index": ALL}, "n_clicks"),
        State("tbl-raw-data",    "data"),
        State("tbl-dom-filter",  "value"),
        State("tbl-sub-filter",  "value"),
        prevent_initial_call=True,
    )
    def open_edit_modal(n_clicks_list, raw_data, dom_filter, sub_filter):
        if not any(n for n in n_clicks_list if n):
            return no_update, no_update, no_update, no_update

        triggered = ctx.triggered_id
        if not triggered or not isinstance(triggered, dict):
            return no_update, no_update, no_update, no_update

        # Re-apply the same filters used in render_table to resolve the row index
        cfg      = get_config() or {}
        tag_cols = cfg.get("tag_columns", [])
        df       = pd.DataFrame(raw_data or [])

        if dom_filter == "<null>" and "Domain" in df.columns:
            df = df[df["Domain"].isna() | (df["Domain"] == "")]
        elif dom_filter and dom_filter != "All" and "Domain" in df.columns:
            df = df[df["Domain"] == dom_filter]

        if sub_filter == "<null>" and "Subdomain" in df.columns:
            df = df[df["Subdomain"].isna() | (df["Subdomain"] == "")]
        elif sub_filter and sub_filter != "All" and "Subdomain" in df.columns:
            df = df[df["Subdomain"] == sub_filter]

        df  = df.reset_index(drop=True)
        idx = triggered["index"]
        if idx >= len(df):
            return no_update, no_update, no_update, no_update

        row       = df.iloc[idx].to_dict()
        full_name = f"{row['catalog_name']}.{row['schema_name']}.{row['table_name']}"

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
            pair = tag_cols[i:i + 2]
            tag_inputs.append(dbc.Row([
                dbc.Col([
                    dbc.Label(pair[0], style={"color": "#9fb3cc", "fontSize": "0.8rem"}),
                    dbc.Input(id={"type": "tag-input", "index": pair[0]},
                              value=current_tags.get(pair[0], ""), type="text",
                              style={"backgroundColor": "#122040", "color": "#e0e0e0",
                                     "border": "1px solid #1E3560"}),
                ], width=6),
                dbc.Col([
                    dbc.Label(pair[1], style={"color": "#9fb3cc", "fontSize": "0.8rem"}) if len(pair) > 1 else html.Div(),
                    dbc.Input(id={"type": "tag-input", "index": pair[1]},
                              value=current_tags.get(pair[1], ""), type="text",
                              style={"backgroundColor": "#122040", "color": "#e0e0e0",
                                     "border": "1px solid #1E3560"}) if len(pair) > 1 else html.Div(),
                ], width=6),
            ], className="mb-3"))

        body = html.Div([
            dbc.Label("Description", style={"color": "#9fb3cc", "fontSize": "0.8rem"}),
            dbc.Textarea(id="edit-desc", value=row.get("description") or "", rows=2,
                         className="mb-3",
                         style={"backgroundColor": "#122040", "color": "#e0e0e0",
                                "border": "1px solid #1E3560"}),
            html.Hr(style={"borderColor": "#1E3560"}) if tag_cols else html.Div(),
            html.P("Tags", className="text-white mb-2 fw-semibold") if tag_cols else html.Div(),
            *tag_inputs,
            html.Div(id="edit-result-msg"),
        ])

        meta = {"row": row, "tag_cols": tag_cols, "full_name": full_name}
        return True, full_name, body, meta

    @app.callback(
        Output("tbl-edit-modal", "is_open", allow_duplicate=True),
        Input("tbl-edit-cancel-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_modal(_):
        return False

    # ── Save edits ───────────────────────────────────────────────────────────────

    @app.callback(
        Output("edit-result-msg",    "children"),
        Output("tbl-refresh-signal", "data"),
        Output("tbl-edit-modal",     "is_open", allow_duplicate=True),
        Input("edit-submit-btn", "n_clicks"),
        State("edit-row-meta", "data"),
        State("edit-desc", "value"),
        State({"type": "tag-input", "index": ALL}, "value"),
        State({"type": "tag-input", "index": ALL}, "id"),
        State("tbl-refresh-signal", "data"),
        prevent_initial_call=True,
    )
    def apply_edit(n_clicks, meta, desc, tag_values, tag_ids, refresh_signal):
        if not n_clicks or not meta:
            return no_update, no_update, no_update

        full_name = meta["full_name"]
        tag_cols  = meta["tag_cols"]
        errors    = []

        safe_desc = (desc or "").replace("'", "\\'")
        try:
            sql(f"COMMENT ON TABLE {full_name} IS '{safe_desc}'")
        except Exception as exc:
            errors.append(f"description: {exc}")

        if tag_cols and tag_values and tag_ids:
            new_tags  = {tid["index"]: val for tid, val in zip(tag_ids, tag_values)}
            desired   = {k: v for k, v in new_tags.items() if k in tag_cols and v and v.strip()}
            to_unset  = [k for k in tag_cols if k not in desired]
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
            return dbc.Alert("; ".join(errors), color="danger"), no_update, no_update
        return html.Div(), (refresh_signal or 0) + 1, False
