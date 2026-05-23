import os
import sys

import dash_bootstrap_components as dbc
from dash import Dash, html, dcc, Input, Output

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
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    title="UC Tag Governance",
)
server = app.server

# ── Register page callbacks ────────────────────────────────────────────────────
overview.register_callbacks(app)
tables.register_callbacks(app)
settings.register_callbacks(app)

# ── Shell layout ───────────────────────────────────────────────────────────────
app.layout = dbc.Container(
    fluid=True,
    children=[
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
    ],
    style={"minHeight": "100vh", "background": "#0d1b2e"},
)


@app.callback(Output("tab-content", "children"), Input("main-tabs", "active_tab"))
def render_tab(tab):
    if tab == "tab-overview":
        return overview.layout()
    if tab == "tab-tables":
        return tables.layout()
    if tab == "tab-settings":
        return settings.layout()
    return html.Div()


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8000)
