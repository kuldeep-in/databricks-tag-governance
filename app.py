import os
import sys

import dash_bootstrap_components as dbc
from dash import Dash, html, dcc

sys.path.insert(0, os.path.dirname(__file__))

from server.config_store import reload_config
from pages import overview, tables, settings

# ── Init config on startup ─────────────────────────────────────────────────────
try:
    reload_config()
except Exception:
    pass

# ── App ────────────────────────────────────────────────────────────────────────
app = Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.DARKLY,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
    ],
    suppress_callback_exceptions=True,
    title="UC Tag Governance",
)
server = app.server

# ── Register page callbacks ────────────────────────────────────────────────────
overview.register_callbacks(app)
tables.register_callbacks(app)
settings.register_callbacks(app)

# ── Shell layout ───────────────────────────────────────────────────────────────
# Tab content is pre-rendered once and kept in the DOM; switching tabs only
# toggles CSS visibility — no callback re-render, no data reload on tab switch.
app.layout = dbc.Container(
    fluid=True,
    children=[
        dcc.Store(id="cfg-version", data=0),   # incremented on every config save
        html.H3("UC Tag Governance", className="mt-3 mb-3 text-white"),
        dbc.Tabs(
            id="main-tabs",
            active_tab="tab-overview",
            children=[
                dbc.Tab(label="📊 Overview",  tab_id="tab-overview",
                        children=html.Div(overview.layout(),  className="mt-3")),
                dbc.Tab(label="📋 Tables",    tab_id="tab-tables",
                        children=html.Div(tables.layout(),    className="mt-3")),
                dbc.Tab(label="⚙️ Configure", tab_id="tab-settings",
                        children=html.Div(settings.layout(),  className="mt-3")),
            ],
        ),
    ],
    style={"minHeight": "100vh", "background": "#0d1b2e"},
)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8000)
