import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, ctx, no_update, ALL

from server.config_store import get_config, reload_config, save_config


def layout():
    cfg = get_config() or {"schemas": [], "tag_columns": [], "exceptions": []}
    return html.Div([
        dcc.Store(id="cfg-schemas-store",    data=cfg.get("schemas",     [])),
        dcc.Store(id="cfg-tags-store",       data=cfg.get("tag_columns", [])),
        dcc.Store(id="cfg-exceptions-store", data=cfg.get("exceptions",  [])),

        # ── Scanned Schemas ────────────────────────────────────────────────────
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

        # ── Tag Names ──────────────────────────────────────────────────────────
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

        # ── Table Exceptions ───────────────────────────────────────────────────
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


def register_callbacks(app):

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
            schemas = [s for i, s in enumerate(schemas) if i != triggered["index"]]
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
        tags      = tags or []
        if triggered == "cfg-add-tag-btn":
            if not new_tag or not new_tag.strip():
                return tags, new_tag, dbc.Alert("Tag name is required.", color="warning")
            t = new_tag.strip()
            if t not in tags:
                tags = tags + [t]
            return tags, "", no_update
        if isinstance(triggered, dict) and triggered.get("type") == "rm-tag":
            tags = [t for i, t in enumerate(tags) if i != triggered["index"]]
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
            exceptions = [e for i, e in enumerate(exceptions) if i != triggered["index"]]
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
            save_config({
                "schemas":     schemas    or [],
                "tag_columns": tags       or [],
                "exceptions":  exceptions or [],
            })
            reload_config()
            return dbc.Alert("Configuration saved successfully.", color="success")
        except Exception as exc:
            return dbc.Alert(f"Save failed: {exc}", color="danger")
