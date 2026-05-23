import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from server.config import INFO_CATALOG, WAREHOUSE_ID, run_sql
from server.config_store import get_config, reload_config, save_config

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="UC Tag Governance",
    page_icon="🏷️",
    layout="wide",
)

COLORS = ["#FF3621", "#00A972", "#FFAB00", "#1B3139", "#8BCAE7", "#AB4057", "#99DDB4", "#FCA4A1"]

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #f5f6f7; }
  [data-testid="stHeader"] { background: #1B3139; }
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
  div[data-testid="metric-container"] {
    background: #fff;
    border-radius: 8px;
    padding: 16px 18px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  }
</style>
""", unsafe_allow_html=True)


# ── SQL helper ─────────────────────────────────────────────────────────────────
def sql(stmt: str) -> list[dict]:
    return run_sql(stmt, warehouse_id=WAREHOUSE_ID)


@st.cache_data(ttl=300, show_spinner=False)
def cached_overview(sf: str, ef: str) -> dict:
    """Cache overview KPIs + distribution data for 5 minutes per filter combination."""
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


@st.cache_data(ttl=300, show_spinner=False)
def cached_tables(sf: str, ef: str, tag_cols_key: str) -> list[dict]:
    """Cache the full table list for 5 minutes. tag_cols_key makes cache key tag-aware."""
    tag_cols = tag_cols_key.split("|") if tag_cols_key else []
    if tag_cols:
        tag_cases = ",\n".join(
            f"MAX(CASE WHEN tg.tag_name='{c}' THEN tg.tag_value END) AS `{c}`"
            for c in tag_cols
        )
    else:
        tag_cases = "NULL AS _no_tags"
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


# ── Schema helpers ─────────────────────────────────────────────────────────────
def resolve_schemas(cfg: dict, catalog: str | None, schema: str | None) -> list[dict]:
    schemas = cfg.get("schemas", [])
    if catalog and schema:
        schemas = [s for s in schemas if s["catalog"] == catalog and s["schema"] == schema]
    elif catalog:
        schemas = [s for s in schemas if s["catalog"] == catalog]
    elif schema:
        schemas = [s for s in schemas if s["schema"] == schema]
    return schemas or cfg.get("schemas", [])


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


# ── Load config on first run ───────────────────────────────────────────────────
if "config_loaded" not in st.session_state:
    try:
        reload_config()
    except Exception as exc:
        st.error(f"Could not load config on startup: {exc}")
    st.session_state.config_loaded = True


# ── Header ─────────────────────────────────────────────────────────────────────
c_logo, c_title = st.columns([0.04, 0.96])
with c_logo:
    st.markdown(
        '<div style="background:#FF3621;border-radius:4px;width:32px;height:32px;'
        'display:flex;align-items:center;justify-content:center;'
        'color:#fff;font-weight:900;font-size:18px;margin-top:4px;">D</div>',
        unsafe_allow_html=True,
    )
with c_title:
    st.markdown("## UC Tag Governance")

st.markdown("---")

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_overview, tab_tables, tab_settings = st.tabs(["📊 Overview", "📋 Tables", "⚙️ Configure"])


# ══════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
with tab_overview:
    cfg = get_config()

    if cfg is None or not cfg.get("schemas"):
        st.info("No schemas configured. Go to the **Configure** tab to add schemas.")
    else:
        schemas_list = cfg.get("schemas", [])
        catalogs     = sorted({s["catalog"] for s in schemas_list})

        c1, c2 = st.columns([2, 2])
        with c1:
            sel_cat = st.selectbox("Catalog", ["All"] + catalogs, key="ov_cat")
        with c2:
            cat_f   = None if sel_cat == "All" else sel_cat
            sch_opts = sorted({s["schema"] for s in schemas_list if not cat_f or s["catalog"] == cat_f})
            sel_sch = st.selectbox("Schema", ["All"] + sch_opts, key="ov_sch")

        sch_f            = None if sel_sch == "All" else sel_sch
        filtered_schemas = resolve_schemas(cfg, cat_f, sch_f)
        exceptions       = cfg.get("exceptions", [])
        sf, ef           = schema_in(filtered_schemas), exc_clause(exceptions)

        with st.spinner("Loading overview…"):
            try:
                result    = cached_overview(sf, ef)
                kpis      = result["kpis"]
                dist_rows = result["dist"]

                k            = kpis[0] if kpis else {}
                total        = int(k.get("total_tables")  or 0)
                fully        = int(k.get("fully_tagged")  or 0)
                no_dom       = int(k.get("no_domain")     or 0)
                no_sub       = int(k.get("no_subdomain")  or 0)
                tagged_pct   = f"{round(fully / total * 100)}%" if total else "0%"

                # KPI row
                m1, m2, m3, m4, m5, m6 = st.columns(6)
                m1.metric("Total Catalogs",    len({s["catalog"] for s in filtered_schemas}))
                m2.metric("Total Schemas",     len(filtered_schemas))
                m3.metric("Total Tables",      total)
                m4.metric("Fully Tagged",      fully,  tagged_pct)
                m5.metric("Missing Domain",    no_dom)
                m6.metric("Missing Subdomain", no_sub)

                st.markdown("")

                # Charts
                by_domain    = [{"domain":     r["label"], "count": int(r["cnt"])} for r in dist_rows if r["metric"] == "domain"]
                by_subdomain = [{"subdomain":  r["label"], "count": int(r["cnt"])} for r in dist_rows if r["metric"] == "subdomain"]
                by_dataclass = [{"data_class": r["label"], "count": int(r["cnt"])} for r in dist_rows if r["metric"] == "dataclass"]

                ch1, ch2, ch3 = st.columns(3)

                with ch1:
                    st.markdown("**Tables by Domain**")
                    if by_domain:
                        df_d = pd.DataFrame(by_domain)
                        fig  = px.bar(df_d, x="count", y="domain", orientation="h",
                                      color_discrete_sequence=["#FF3621"])
                        fig.update_layout(height=280, margin=dict(l=0, r=10, t=10, b=0),
                                          yaxis_title="", xaxis_title="")
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.caption("No Domain tags applied yet")

                with ch2:
                    st.markdown("**Tables by Subdomain**")
                    if by_subdomain:
                        df_s = pd.DataFrame(by_subdomain)
                        fig  = px.bar(df_s, x="count", y="subdomain", orientation="h",
                                      color_discrete_sequence=["#00A972"])
                        fig.update_layout(height=280, margin=dict(l=0, r=10, t=10, b=0),
                                          yaxis_title="", xaxis_title="")
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.caption("No Subdomain tags applied yet")

                with ch3:
                    st.markdown("**DataClass Distribution**")
                    if by_dataclass:
                        df_dc = pd.DataFrame(by_dataclass)
                        fig   = px.pie(df_dc, values="count", names="data_class",
                                       color_discrete_sequence=COLORS)
                        fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0))
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.caption("No DataClass tags applied yet")

            except Exception as exc:
                st.error(f"Error loading overview: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# TABLES
# ══════════════════════════════════════════════════════════════════════════════
with tab_tables:
    cfg = get_config()

    if cfg is None or not cfg.get("schemas"):
        st.info("No schemas configured. Go to the **Configure** tab to add schemas.")
    else:
        schemas_list = cfg.get("schemas", [])
        tag_cols     = cfg.get("tag_columns", [])

        # Top filters
        fc1, fc2, fc3 = st.columns([2, 2, 3])
        with fc1:
            catalogs  = sorted({s["catalog"] for s in schemas_list})
            tbl_cat   = st.selectbox("Catalog", ["All"] + catalogs, key="tbl_cat")
        with fc2:
            cat_f2    = None if tbl_cat == "All" else tbl_cat
            sch_opts2 = sorted({s["schema"] for s in schemas_list if not cat_f2 or s["catalog"] == cat_f2})
            tbl_sch   = st.selectbox("Schema", ["All"] + sch_opts2, key="tbl_sch")
        with fc3:
            search = st.text_input("Search tables", placeholder="Search by name, tag…", key="tbl_search")

        sch_f2           = None if tbl_sch == "All" else tbl_sch
        filtered_schemas = resolve_schemas(cfg, cat_f2, sch_f2)
        exceptions       = cfg.get("exceptions", [])
        sf, ef           = schema_in(filtered_schemas), exc_clause(exceptions)

        with st.spinner("Loading tables…"):
            try:
                tag_cols_key = "|".join(tag_cols)
                rows = cached_tables(sf, ef, tag_cols_key)

                df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["catalog_name", "schema_name", "table_name", "description"])
                if "_no_tags" in df.columns:
                    df.drop(columns=["_no_tags"], inplace=True)

                # Search
                if search and not df.empty:
                    mask = df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
                    df   = df[mask]

                # Column filters
                ff1, ff2 = st.columns([2, 2])
                with ff1:
                    if "Domain" in df.columns:
                        domain_opts = ["All"] + sorted(df["Domain"].dropna().unique().tolist())
                        sel_dom = st.selectbox("Filter Domain", domain_opts, key="tbl_dom")
                        if sel_dom != "All":
                            df = df[df["Domain"] == sel_dom]
                with ff2:
                    if "Subdomain" in df.columns:
                        sub_opts = ["All"] + sorted(df["Subdomain"].dropna().unique().tolist())
                        sel_sub = st.selectbox("Filter Subdomain", sub_opts, key="tbl_sub")
                        if sel_sub != "All":
                            df = df[df["Subdomain"] == sel_sub]

                st.caption(f'{len(df)} table{"s" if len(df) != 1 else ""}')

                DISPLAY_COLS = ["catalog_name", "schema_name", "table_name", "description"] + \
                               [c for c in tag_cols if c in df.columns]

                event = st.dataframe(
                    df[DISPLAY_COLS] if not df.empty else pd.DataFrame(columns=DISPLAY_COLS),
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="tbl_df",
                )

                selected = event.selection.rows
                if selected and not df.empty:
                    row = df.iloc[selected[0]].to_dict()
                    full_name = f"{row['catalog_name']}.{row['schema_name']}.{row['table_name']}"

                    st.divider()
                    st.subheader(f"Edit: {full_name}")

                    with st.spinner("Loading current tags…"):
                        tag_rows = sql(f"""
                            SELECT tag_name, tag_value
                            FROM {INFO_CATALOG}.information_schema.table_tags
                            WHERE catalog_name='{row['catalog_name']}'
                              AND schema_name='{row['schema_name']}'
                              AND table_name='{row['table_name']}'
                        """)
                        current_tags = {r["tag_name"]: r["tag_value"] for r in tag_rows}

                    with st.form("edit_form", clear_on_submit=False):
                        new_desc = st.text_area("Description", value=row.get("description") or "")

                        if tag_cols:
                            st.markdown("**Tags**")
                            cols_grid = st.columns(2)
                            new_tags  = {}
                            for i, col in enumerate(tag_cols):
                                with cols_grid[i % 2]:
                                    new_tags[col] = st.text_input(
                                        col, value=current_tags.get(col, ""), key=f"etag_{col}"
                                    )

                        submitted = st.form_submit_button("✅ Apply Changes", type="primary")

                    if submitted:
                        errors = []
                        safe_desc = new_desc.replace("'", "\\'")
                        try:
                            sql(f"COMMENT ON TABLE {full_name} IS '{safe_desc}'")
                        except Exception as exc:
                            errors.append(f"description: {exc}")

                        if tag_cols:
                            desired  = {k: v for k, v in new_tags.items() if v.strip()}
                            to_unset = [k for k in tag_cols if k not in desired]

                            if desired:
                                tag_str = ", ".join(
                                    f"'{k}' = '{v.replace(chr(39), chr(39)*2)}'" for k, v in desired.items()
                                )
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
                            st.error("; ".join(errors))
                        else:
                            st.success(f"Updated {full_name}")
                            st.rerun()

            except Exception as exc:
                st.error(f"Error loading tables: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURE / SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
with tab_settings:
    cfg = get_config() or {"schemas": [], "tag_columns": [], "exceptions": []}

    # Initialise session state once from saved config
    if "cfg_schemas" not in st.session_state:
        st.session_state.cfg_schemas    = list(cfg.get("schemas",     []))
        st.session_state.cfg_tags       = list(cfg.get("tag_columns", []))
        st.session_state.cfg_exceptions = list(cfg.get("exceptions",  []))

    # ── Scanned Schemas ────────────────────────────────────────────────────────
    st.subheader("Scanned Schemas")
    st.caption("Catalog + schema pairs the app will scan for tables and tags.")

    for i, s in enumerate(st.session_state.cfg_schemas):
        r1, r2 = st.columns([10, 1])
        with r1:
            st.markdown(f"**{s['catalog']}** · {s['schema']}")
        with r2:
            if st.button("✕", key=f"rm_s_{i}"):
                st.session_state.cfg_schemas.pop(i)
                st.rerun()

    if not st.session_state.cfg_schemas:
        st.caption("No schemas configured.")

    with st.form("add_schema_form"):
        a1, a2, a3 = st.columns([3, 3, 1])
        with a1:
            ns_cat = st.text_input("Catalog name", placeholder="catalog_name", label_visibility="collapsed")
        with a2:
            ns_sch = st.text_input("Schema name",  placeholder="schema_name",  label_visibility="collapsed")
        with a3:
            if st.form_submit_button("＋ Add"):
                if ns_cat.strip() and ns_sch.strip():
                    entry = {"catalog": ns_cat.strip(), "schema": ns_sch.strip()}
                    if entry not in st.session_state.cfg_schemas:
                        st.session_state.cfg_schemas.append(entry)
                    st.rerun()

    st.markdown("---")

    # ── Tag Names ──────────────────────────────────────────────────────────────
    st.subheader("Tag Names")
    st.caption("Tag keys that will be displayed, edited, and applied to tables.")

    for i, t in enumerate(st.session_state.cfg_tags):
        t1, t2 = st.columns([10, 1])
        with t1:
            st.code(t, language=None)
        with t2:
            if st.button("✕", key=f"rm_t_{i}"):
                st.session_state.cfg_tags.pop(i)
                st.rerun()

    if not st.session_state.cfg_tags:
        st.caption("No tags configured.")

    with st.form("add_tag_form"):
        b1, b2 = st.columns([5, 1])
        with b1:
            new_tag = st.text_input("Tag name", placeholder="TagName", label_visibility="collapsed")
        with b2:
            if st.form_submit_button("＋ Add"):
                if new_tag.strip() and new_tag.strip() not in st.session_state.cfg_tags:
                    st.session_state.cfg_tags.append(new_tag.strip())
                    st.rerun()

    st.markdown("---")

    # ── Table Exceptions ───────────────────────────────────────────────────────
    st.subheader("Table Exceptions")
    st.caption("Tables excluded from all scans, counts, and the table list.")

    for i, e in enumerate(st.session_state.cfg_exceptions):
        e1, e2 = st.columns([10, 1])
        with e1:
            st.markdown(f"{e['catalog']}.**{e['schema']}**.{e['table']}")
        with e2:
            if st.button("✕", key=f"rm_e_{i}"):
                st.session_state.cfg_exceptions.pop(i)
                st.rerun()

    if not st.session_state.cfg_exceptions:
        st.caption("No exceptions — all tables in scanned schemas are included.")

    with st.form("add_exc_form"):
        x1, x2, x3, x4 = st.columns([3, 3, 3, 1])
        with x1:
            exc_cat = st.text_input("Catalog",    placeholder="catalog",    label_visibility="collapsed")
        with x2:
            exc_sch = st.text_input("Schema",     placeholder="schema",     label_visibility="collapsed")
        with x3:
            exc_tbl = st.text_input("Table name", placeholder="table_name", label_visibility="collapsed")
        with x4:
            if st.form_submit_button("＋ Add"):
                if exc_cat.strip() and exc_sch.strip() and exc_tbl.strip():
                    entry = {"catalog": exc_cat.strip(), "schema": exc_sch.strip(), "table": exc_tbl.strip()}
                    if entry not in st.session_state.cfg_exceptions:
                        st.session_state.cfg_exceptions.append(entry)
                    st.rerun()

    st.markdown("---")

    # ── Save ──────────────────────────────────────────────────────────────────
    if st.button("💾 Save Configuration", type="primary"):
        try:
            data = {
                "schemas":     st.session_state.cfg_schemas,
                "tag_columns": st.session_state.cfg_tags,
                "exceptions":  st.session_state.cfg_exceptions,
            }
            save_config(data)
            reload_config()
            # Reset session state so next visit reflects saved values
            for k in ["cfg_schemas", "cfg_tags", "cfg_exceptions"]:
                del st.session_state[k]
            st.success("Configuration saved successfully.")
            st.rerun()
        except Exception as exc:
            st.error(f"Save failed: {exc}")
