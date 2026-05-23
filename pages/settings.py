import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, ctx, no_update, ALL

from server.config_store import get_config, reload_config, save_config

_CARD_STYLE = {"background": "#0a1628", "border": "1px solid #1E3560"}
_HEADER_STYLE = {"background": "#0e1c36", "borderBottom": "1px solid #1E3560"}


def layout():
    cfg = get_config() or {"schemas": [], "tag_columns": [], "exceptions": []}
    return html.Div([
        dcc.Store(id="cfg-schemas-store",    data=cfg.get("schemas",     [])),
        dcc.Store(id="cfg-tags-store",       data=cfg.get("tag_columns", [])),
        dcc.Store(id="cfg-exceptions-store", data=cfg.get("exceptions",  [])),
        dcc.Store(id="cfg-save-section",     data=None),

        # ── Confirmation Modal ─────────────────────────────────────────────────
        dbc.Modal([
            dbc.ModalHeader(
                dbc.ModalTitle("Confirm Save", className="text-white"),
                style=_HEADER_STYLE,
                close_button=True,
            ),
            dbc.ModalBody(id="cfg-confirm-body", style={"background": "#0a1628"}),
            dbc.ModalFooter([
                dbc.Button("Cancel", id="cfg-confirm-cancel", color="secondary",
                           outline=True, className="me-2"),
                dbc.Button("Confirm Save", id="cfg-confirm-ok", color="primary"),
            ], style={"background": "#0a1628", "borderTop": "1px solid #1E3560"}),
        ], id="cfg-confirm-modal", is_open=False, centered=True, backdrop="static"),

        # ── 3-Column Layout ────────────────────────────────────────────────────
        dbc.Row([

            # ── Column 1: Scanned Schemas ──────────────────────────────────────
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(
                        html.H6("Scanned Schemas", className="text-white mb-0"),
                        style=_HEADER_STYLE,
                    ),
                    dbc.CardBody([
                        html.P("Schemas the app will scan — enter as catalog.schema.",
                               className="text-muted small mb-3"),
                        html.Div(id="cfg-schemas-list", className="mb-3",
                                 style={"minHeight": "60px", "maxHeight": "260px",
                                        "overflowY": "auto"}),
                        dbc.InputGroup([
                            dbc.Input(id="cfg-new-schema", placeholder="catalog.schema",
                                      type="text", size="sm"),
                            dbc.Button("+ Add", id="cfg-add-schema-btn",
                                       color="secondary", size="sm"),
                        ], className="mb-1"),
                        html.Div(id="cfg-schema-add-msg", className="mb-2"),
                        dbc.Button("💾 Save Schemas", id="cfg-save-schemas-btn",
                                   color="primary", size="sm", className="w-100 mt-2"),
                        html.Div(id="cfg-schemas-save-msg", className="mt-2"),
                    ]),
                ], className="h-100", style=_CARD_STYLE),
            ], width=4),

            # ── Column 2: Tag Names ────────────────────────────────────────────
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(
                        html.H6("Tag Names", className="text-white mb-0"),
                        style=_HEADER_STYLE,
                    ),
                    dbc.CardBody([
                        html.P("Tag keys displayed, edited, and applied to tables.",
                               className="text-muted small mb-3"),
                        html.Div(id="cfg-tags-list", className="mb-3",
                                 style={"minHeight": "60px", "maxHeight": "260px",
                                        "overflowY": "auto"}),
                        dbc.InputGroup([
                            dbc.Input(id="cfg-new-tag", placeholder="TagName",
                                      type="text", size="sm"),
                            dbc.Button("+ Add", id="cfg-add-tag-btn",
                                       color="secondary", size="sm"),
                        ], className="mb-1"),
                        html.Div(id="cfg-tag-add-msg", className="mb-2"),
                        dbc.Button("💾 Save Tags", id="cfg-save-tags-btn",
                                   color="primary", size="sm", className="w-100 mt-2"),
                        html.Div(id="cfg-tags-save-msg", className="mt-2"),
                    ]),
                ], className="h-100", style=_CARD_STYLE),
            ], width=4),

            # ── Column 3: Table Exceptions ─────────────────────────────────────
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(
                        html.H6("Table Exceptions", className="text-white mb-0"),
                        style=_HEADER_STYLE,
                    ),
                    dbc.CardBody([
                        html.P("Tables excluded from scans — enter as catalog.schema.table.",
                               className="text-muted small mb-3"),
                        html.Div(id="cfg-exceptions-list", className="mb-3",
                                 style={"minHeight": "60px", "maxHeight": "260px",
                                        "overflowY": "auto"}),
                        dbc.InputGroup([
                            dbc.Input(id="cfg-new-exception",
                                      placeholder="catalog.schema.table",
                                      type="text", size="sm"),
                            dbc.Button("+ Add", id="cfg-add-exc-btn",
                                       color="secondary", size="sm"),
                        ], className="mb-1"),
                        html.Div(id="cfg-exc-add-msg", className="mb-2"),
                        dbc.Button("💾 Save Exceptions", id="cfg-save-exc-btn",
                                   color="primary", size="sm", className="w-100 mt-2"),
                        html.Div(id="cfg-exc-save-msg", className="mt-2"),
                    ]),
                ], className="h-100", style=_CARD_STYLE),
            ], width=4),

        ], className="g-3"),
    ])


def register_callbacks(app):

    # ── Render lists ───────────────────────────────────────────────────────────

    @app.callback(
        Output("cfg-schemas-list", "children"),
        Input("cfg-schemas-store", "data"),
    )
    def render_schemas_list(schemas):
        if not schemas:
            return html.P("No schemas configured.", className="text-muted small")
        return [
            dbc.Row([
                dbc.Col(
                    html.Span(f"{s['catalog']}.{s['schema']}",
                              className="text-white small font-monospace"),
                    width=10,
                ),
                dbc.Col(
                    dbc.Button("✕", id={"type": "rm-schema", "index": i},
                               color="danger", size="sm", className="py-0 px-1"),
                    width=2,
                ),
            ], className="mb-1 align-items-center")
            for i, s in enumerate(schemas)
        ]

    @app.callback(
        Output("cfg-tags-list", "children"),
        Input("cfg-tags-store", "data"),
    )
    def render_tags_list(tags):
        if not tags:
            return html.P("No tags configured.", className="text-muted small")
        return [
            dbc.Row([
                dbc.Col(
                    dbc.Badge(t, color="info", className="me-1 font-monospace"),
                    width=10,
                ),
                dbc.Col(
                    dbc.Button("✕", id={"type": "rm-tag", "index": i},
                               color="danger", size="sm", className="py-0 px-1"),
                    width=2,
                ),
            ], className="mb-1 align-items-center")
            for i, t in enumerate(tags)
        ]

    @app.callback(
        Output("cfg-exceptions-list", "children"),
        Input("cfg-exceptions-store", "data"),
    )
    def render_exceptions_list(exceptions):
        if not exceptions:
            return html.P("No exceptions configured.", className="text-muted small")
        return [
            dbc.Row([
                dbc.Col(
                    html.Span(f"{e['catalog']}.{e['schema']}.{e['table']}",
                              className="text-white small font-monospace"),
                    width=10,
                ),
                dbc.Col(
                    dbc.Button("✕", id={"type": "rm-exc", "index": i},
                               color="danger", size="sm", className="py-0 px-1"),
                    width=2,
                ),
            ], className="mb-1 align-items-center")
            for i, e in enumerate(exceptions)
        ]

    # ── Add / Remove ───────────────────────────────────────────────────────────

    @app.callback(
        Output("cfg-schemas-store",   "data"),
        Output("cfg-new-schema",      "value"),
        Output("cfg-schema-add-msg",  "children"),
        Input("cfg-add-schema-btn",   "n_clicks"),
        Input({"type": "rm-schema", "index": ALL}, "n_clicks"),
        State("cfg-schemas-store",    "data"),
        State("cfg-new-schema",       "value"),
        prevent_initial_call=True,
    )
    def manage_schemas(add_clicks, rm_clicks, schemas, new_val):
        triggered = ctx.triggered_id
        schemas   = schemas or []
        if triggered == "cfg-add-schema-btn":
            v = (new_val or "").strip()
            if not v:
                return schemas, new_val, dbc.Alert("Enter a schema.", color="warning", duration=3000)
            parts = v.split(".")
            if len(parts) != 2 or not all(parts):
                return schemas, new_val, dbc.Alert(
                    "Use catalog.schema format (exactly one dot).", color="warning", duration=3000)
            entry = {"catalog": parts[0], "schema": parts[1]}
            if entry not in schemas:
                schemas = schemas + [entry]
            return schemas, "", no_update
        if isinstance(triggered, dict) and triggered.get("type") == "rm-schema":
            if not ctx.triggered[0]["value"]:
                return no_update, no_update, no_update
            schemas = [s for i, s in enumerate(schemas) if i != triggered["index"]]
            return schemas, no_update, no_update
        return no_update, no_update, no_update

    @app.callback(
        Output("cfg-tags-store",   "data"),
        Output("cfg-new-tag",      "value"),
        Output("cfg-tag-add-msg",  "children"),
        Input("cfg-add-tag-btn",   "n_clicks"),
        Input({"type": "rm-tag", "index": ALL}, "n_clicks"),
        State("cfg-tags-store",    "data"),
        State("cfg-new-tag",       "value"),
        prevent_initial_call=True,
    )
    def manage_tags(add_clicks, rm_clicks, tags, new_tag):
        triggered = ctx.triggered_id
        tags      = tags or []
        if triggered == "cfg-add-tag-btn":
            t = (new_tag or "").strip()
            if not t:
                return tags, new_tag, dbc.Alert("Tag name is required.", color="warning", duration=3000)
            if t not in tags:
                tags = tags + [t]
            return tags, "", no_update
        if isinstance(triggered, dict) and triggered.get("type") == "rm-tag":
            if not ctx.triggered[0]["value"]:
                return no_update, no_update, no_update
            tags = [t for i, t in enumerate(tags) if i != triggered["index"]]
            return tags, no_update, no_update
        return no_update, no_update, no_update

    @app.callback(
        Output("cfg-exceptions-store",  "data"),
        Output("cfg-new-exception",     "value"),
        Output("cfg-exc-add-msg",       "children"),
        Input("cfg-add-exc-btn",        "n_clicks"),
        Input({"type": "rm-exc", "index": ALL}, "n_clicks"),
        State("cfg-exceptions-store",   "data"),
        State("cfg-new-exception",      "value"),
        prevent_initial_call=True,
    )
    def manage_exceptions(add_clicks, rm_clicks, exceptions, new_val):
        triggered  = ctx.triggered_id
        exceptions = exceptions or []
        if triggered == "cfg-add-exc-btn":
            v = (new_val or "").strip()
            if not v:
                return exceptions, new_val, dbc.Alert("Enter an exception.", color="warning", duration=3000)
            parts = v.split(".")
            if len(parts) != 3 or not all(parts):
                return exceptions, new_val, dbc.Alert(
                    "Use catalog.schema.table format (exactly two dots).", color="warning", duration=3000)
            entry = {"catalog": parts[0], "schema": parts[1], "table": parts[2]}
            if entry not in exceptions:
                exceptions = exceptions + [entry]
            return exceptions, "", no_update
        if isinstance(triggered, dict) and triggered.get("type") == "rm-exc":
            if not ctx.triggered[0]["value"]:
                return no_update, no_update, no_update
            exceptions = [e for i, e in enumerate(exceptions) if i != triggered["index"]]
            return exceptions, no_update, no_update
        return no_update, no_update, no_update

    # ── Open confirmation modal ────────────────────────────────────────────────

    @app.callback(
        Output("cfg-confirm-modal",  "is_open"),
        Output("cfg-confirm-body",   "children"),
        Output("cfg-save-section",   "data"),
        Input("cfg-save-schemas-btn", "n_clicks"),
        Input("cfg-save-tags-btn",    "n_clicks"),
        Input("cfg-save-exc-btn",     "n_clicks"),
        Input("cfg-confirm-cancel",   "n_clicks"),
        State("cfg-schemas-store",    "data"),
        State("cfg-tags-store",       "data"),
        State("cfg-exceptions-store", "data"),
        prevent_initial_call=True,
    )
    def open_confirm_modal(save_s, save_t, save_e, cancel, schemas, tags, exceptions):
        triggered = ctx.triggered_id
        if triggered == "cfg-confirm-cancel":
            return False, no_update, no_update

        if triggered == "cfg-save-schemas-btn":
            section = "schemas"
            items   = schemas or []
            title   = f"Save {len(items)} schema(s) to configuration?"
            rows    = [html.Li(f"{s['catalog']}.{s['schema']}", className="font-monospace small")
                       for s in items] or [html.Li("(none — will clear all schemas)", className="text-muted")]

        elif triggered == "cfg-save-tags-btn":
            section = "tags"
            items   = tags or []
            title   = f"Save {len(items)} tag(s) to configuration?"
            rows    = [html.Li(t, className="font-monospace small") for t in items] \
                      or [html.Li("(none — will clear all tags)", className="text-muted")]

        elif triggered == "cfg-save-exc-btn":
            section = "exceptions"
            items   = exceptions or []
            title   = f"Save {len(items)} exception(s) to configuration?"
            rows    = [html.Li(f"{e['catalog']}.{e['schema']}.{e['table']}",
                               className="font-monospace small") for e in items] \
                      or [html.Li("(none — no exceptions)", className="text-muted")]

        else:
            return no_update, no_update, no_update

        body = html.Div([
            html.P(title, className="text-white fw-semibold mb-2"),
            html.Ul(rows, className="text-light mb-0"),
        ])
        return True, body, section

    # ── Perform save after confirmation ────────────────────────────────────────

    @app.callback(
        Output("cfg-confirm-modal",   "is_open",  allow_duplicate=True),
        Output("cfg-schemas-save-msg", "children"),
        Output("cfg-tags-save-msg",    "children"),
        Output("cfg-exc-save-msg",     "children"),
        Output("cfg-version",          "data"),
        Input("cfg-confirm-ok",        "n_clicks"),
        State("cfg-save-section",      "data"),
        State("cfg-schemas-store",     "data"),
        State("cfg-tags-store",        "data"),
        State("cfg-exceptions-store",  "data"),
        State("cfg-version",           "data"),
        running=[
            (Output("cfg-confirm-ok", "disabled"), True,       False),
            (Output("cfg-confirm-ok", "children"), "Saving…",  "Confirm Save"),
        ],
        prevent_initial_call=True,
    )
    def do_save(n, section, schemas, tags, exceptions, version):
        if not n or not section:
            return no_update, no_update, no_update, no_update, no_update

        existing = get_config() or {"schemas": [], "tag_columns": [], "exceptions": []}
        next_ver = (version or 0) + 1

        try:
            if section == "schemas":
                save_config({
                    "schemas":     schemas or [],
                    "tag_columns": existing.get("tag_columns", []),
                    "exceptions":  existing.get("exceptions",  []),
                })
                reload_config()
                return False, \
                    dbc.Alert("Schemas saved.", color="success", duration=4000), \
                    no_update, no_update, next_ver

            elif section == "tags":
                save_config({
                    "schemas":     existing.get("schemas",  []),
                    "tag_columns": tags or [],
                    "exceptions":  existing.get("exceptions", []),
                })
                reload_config()
                return False, no_update, \
                    dbc.Alert("Tags saved.", color="success", duration=4000), \
                    no_update, next_ver

            elif section == "exceptions":
                save_config({
                    "schemas":     existing.get("schemas",     []),
                    "tag_columns": existing.get("tag_columns", []),
                    "exceptions":  exceptions or [],
                })
                reload_config()
                return False, no_update, no_update, \
                    dbc.Alert("Exceptions saved.", color="success", duration=4000), next_ver

        except Exception as exc:
            msg = dbc.Alert(f"Save failed: {exc}", color="danger")
            if section == "schemas":
                return False, msg, no_update, no_update, no_update
            elif section == "tags":
                return False, no_update, msg, no_update, no_update
            else:
                return False, no_update, no_update, msg, no_update

        return False, no_update, no_update, no_update, no_update
