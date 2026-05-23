import pandas as pd
import plotly.express as px
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State

from server.config_store import get_config
from utils import (
    COLORS, CHART_DOMAIN, CHART_SUB, PLOTLY_TMPL,
    fetch_overview, resolve_schemas, schema_in, exc_clause, metric_card,
)


def layout():
    cfg = get_config()
    if cfg is None or not cfg.get("schemas"):
        return dbc.Alert("No schemas configured. Go to the ⚙️ Configure tab to add schemas.", color="info")

    catalogs = sorted({s["catalog"] for s in cfg["schemas"]})
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


def register_callbacks(app):

    @app.callback(
        Output("ov-sch", "options"),
        Output("ov-sch", "value"),
        Input("ov-cat", "value"),
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

        cat_f      = None if cat == "All" else cat
        sch_f      = None if sch == "All" else sch
        filtered   = resolve_schemas(cfg, cat_f, sch_f)
        exceptions = cfg.get("exceptions", [])
        sf, ef     = schema_in(filtered), exc_clause(exceptions)

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
