"""
Big CSV / Excel Explorer
------------------------
A Streamlit tool for value counts, pivots and filters on files of any size
(10 lakh / 10 crore+ rows). Data is loaded into DuckDB (a fast, embedded
analytics engine), so all heavy work happens in SQL, not in pandas / Excel.

Run:  python app.py      (starts with no upload limit and the app's theme)
"""

import io
import hashlib
import inspect
import os
import re
import tempfile
import time

import sys

import duckdb
import pandas as pd
import streamlit as st

UPLOAD_LIMIT_MB = 100_000  # 100 GB: effectively unlimited

# "Indigo Mist" theme, in a light and a dark version.
LIGHT = {"primaryColor": "#5B4BDB", "backgroundColor": "#F6F7FB",
         "secondaryBackgroundColor": "#ECEEF8", "textColor": "#1F2340"}
DARK = {"primaryColor": "#8B7CF6", "backgroundColor": "#0F1020",
        "secondaryBackgroundColor": "#1D1E36", "textColor": "#E7E7F7"}
LIGHT_SIDEBAR = {"backgroundColor": "#ECEAFB", "secondaryBackgroundColor": "#FFFFFF"}
DARK_SIDEBAR = {"backgroundColor": "#17182D", "secondaryBackgroundColor": "#24264A"}


def theme_flags() -> list:
    """Command-line theme settings that this Streamlit version understands."""
    from streamlit import config as _cfg
    known = set(getattr(_cfg, "_config_options_template", {}))
    flags = []
    if "theme.dark.primaryColor" in known:  # newer Streamlit: own light AND dark theme
        for mode, pal, side in (("light", LIGHT, LIGHT_SIDEBAR), ("dark", DARK, DARK_SIDEBAR)):
            flags += [f"--theme.{mode}.{k}={v}" for k, v in pal.items()]
            if f"theme.{mode}.sidebar.backgroundColor" in known:
                flags += [f"--theme.{mode}.sidebar.{k}={v}" for k, v in side.items()]
    else:  # older Streamlit: one custom (light) theme; Dark mode still works via CSS
        flags += ["--theme.base=light"] + [f"--theme.{k}={v}" for k, v in LIGHT.items()]
    return flags


if __name__ == "__main__" and not st.runtime.exists():
    # `python app.py` -> start Streamlit with the big upload limit and the theme,
    # from any folder.
    from streamlit.web import cli as stcli
    sys.argv = ["streamlit", "run", os.path.abspath(__file__),
                f"--server.maxUploadSize={UPLOAD_LIMIT_MB}",
                "--server.maxMessageSize=2000", *theme_flags(), *sys.argv[1:]]
    sys.exit(stcli.main())

st.set_page_config(page_title="Big CSV Explorer", page_icon="📊", layout="wide")

# Styling uses see-through tints and inherits text colours, so it looks right in
# BOTH light and dark mode (and with any Streamlit theme).
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {
    --acc: #7B6CF0;             /* violet accent: readable on light and dark */
    --acc-strong: #5B4BDB;
    --tint: rgba(123, 108, 240, 0.10);
    --tint-strong: rgba(123, 108, 240, 0.18);
    --line: rgba(128, 128, 170, 0.28);
    --card: rgba(128, 128, 170, 0.07);
}
html, body, .stApp, .stMarkdown, button, input, textarea, select {
    font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}
.block-container { padding-top: 3.2rem; }

/* Sidebar: soft violet glow on top of the theme's own background */
section[data-testid="stSidebar"] {
    background-image: linear-gradient(180deg, rgba(123,108,240,0.20) 0%,
                                      rgba(123,108,240,0.06) 45%, rgba(123,108,240,0) 100%);
    border-right: 1px solid var(--line);
}
section[data-testid="stSidebar"] h1 { font-size: 1.35rem; }

/* Hero banner (white text on violet works in both modes) */
.hero {
    background: linear-gradient(120deg, #4C3FD1 0%, #7B5CF0 55%, #A57BF5 100%);
    border-radius: 16px; padding: 1.15rem 1.5rem; margin-bottom: 1.1rem;
    box-shadow: 0 8px 26px rgba(76, 63, 209, 0.28);
}
.hero h1 { color: #FFFFFF !important; font-size: 1.6rem; font-weight: 700; margin: 0; padding: 0; }
.hero p  { color: rgba(255,255,255,0.86) !important; margin: 0.25rem 0 0 0; font-size: 0.95rem; }

/* Metric cards */
div[data-testid="stMetric"] {
    background: var(--card); border: 1px solid var(--line); border-radius: 14px;
    padding: 0.8rem 1rem; border-top: 3px solid var(--acc);
}
div[data-testid="stMetric"] label { opacity: 0.75; }
div[data-testid="stMetricValue"] { color: var(--acc); font-weight: 700; }
div[data-testid="stMetricValue"] > div { font-size: 1.7rem; }

/* Tabs */
.stTabs [role="tablist"] { gap: 0.4rem; border-bottom: 1px solid var(--line); }
.stTabs [role="tab"] {
    background: var(--tint); border-radius: 10px 10px 0 0; padding: 0.45rem 1rem;
    font-weight: 600;
}
.stTabs [role="tab"][aria-selected="true"] { background: var(--acc-strong); color: #FFFFFF; }
.stTabs [role="tab"][aria-selected="true"] p { color: #FFFFFF; }

/* Buttons */
.stButton > button, .stDownloadButton > button { border-radius: 10px; font-weight: 600; }
.stButton > button[kind="primary"] {
    background: linear-gradient(120deg, #4C3FD1, #7B5CF0); border: none; color: #FFFFFF;
}

/* Hide hosting branding inside the app: Fork / GitHub / Deploy buttons and the
   coloured top line. The sidebar toggle and the ⋮ menu (theme switch) stay. */
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"], .stAppDeployButton,
[data-testid="stDecoration"], footer, [class*="viewerBadge"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent; }

/* Upload box, tables, expanders */
div[data-testid="stFileUploader"] section {
    border-radius: 12px; background: var(--tint); border: 1.5px dashed var(--acc);
}
div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden;
    border: 1px solid var(--line); }
div[data-testid="stExpander"] details { border-radius: 12px; border-color: var(--line);
    background: var(--card); }
</style>
""", unsafe_allow_html=True)


def hero(title: str, subtitle: str):
    st.markdown(f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>',
                unsafe_allow_html=True)

WORKDIR = os.path.join(tempfile.gettempdir(), "big_csv_explorer")
os.makedirs(WORKDIR, exist_ok=True)

PREVIEW_ROWS = 2000          # rows shown on screen for big results
EXCEL_MAX_ROWS = 1_048_575   # Excel sheet limit (minus header)
MAX_PIVOT_COLUMNS = 500      # guard against exploding column fields
FILE_TYPES = ["csv", "txt", "tsv", "xlsx", "xlsm", "xls", "xlsb", "parquet"]
NUMERIC_PREFIXES = ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT",
                    "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT", "FLOAT", "DOUBLE",
                    "REAL", "DECIMAL")


# ----------------------------------------------------------------------------
# DuckDB helpers
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# Compatibility with older Streamlit versions
# ----------------------------------------------------------------------------
def _full_width(fn) -> dict:
    """Newer Streamlit uses width='stretch'; older versions use use_container_width."""
    try:
        p = inspect.signature(fn).parameters.get("width")
        if p is not None and "Width" in str(p.annotation):  # accepts "stretch"
            return {"width": "stretch"}
    except (TypeError, ValueError):
        pass
    return {"use_container_width": True}


FULL_BTN = _full_width(st.button)
FULL_DF = _full_width(st.dataframe)
FULL_CHART = _full_width(st.altair_chart)
_DL_PARAMS = inspect.signature(st.download_button).parameters
DL_IGNORE = {"on_click": "ignore"} if "on_click" in _DL_PARAMS else {}


@st.cache_resource
def get_engine():
    # A database file on disk (not RAM): handles files far bigger than memory.
    for f in os.listdir(WORKDIR):  # clean up databases from earlier runs
        if f.startswith("session_") and f.endswith((".duckdb", ".duckdb.wal")):
            try:
                os.remove(os.path.join(WORKDIR, f))
            except OSError:
                pass  # still in use by another running copy
    db = os.path.join(WORKDIR, f"session_{os.getpid()}.duckdb")
    con = duckdb.connect(db, config={"temp_directory": os.path.join(WORKDIR, "spill")})
    return {"con": con, "version": 0}


def con():
    return get_engine()["con"].cursor()


def bump_version():
    get_engine()["version"] += 1


def qi(name) -> str:
    """Quote an identifier (column / table name)."""
    return '"' + str(name).replace('"', '""') + '"'


def ql(value) -> str:
    """Quote a string literal."""
    return "'" + str(value).replace("'", "''") + "'"


def is_numeric(dtype: str) -> bool:
    return dtype.upper().startswith(NUMERIC_PREFIXES)


@st.cache_data(show_spinner=False, max_entries=300)
def _cached_query(sql: str, token: str) -> pd.DataFrame:
    return con().execute(sql).df()


def query(sql: str) -> pd.DataFrame:
    """Run a query; results are cached until the data or filters change."""
    return _cached_query(sql, st.session_state.get("cache_token", ""))


def scalar(sql: str):
    return query(sql).iat[0, 0]


def columns_of(rel: str) -> dict:
    df = con().execute(f"DESCRIBE SELECT * FROM {rel}").df()
    return dict(zip(df["column_name"], df["column_type"]))


def table_exists(name: str) -> bool:
    return bool(con().execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [name]
    ).fetchone()[0])


# ----------------------------------------------------------------------------
# File loading
# ----------------------------------------------------------------------------
def file_kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm", ".xls", ".xlsb"):
        return "excel"
    if ext == ".parquet":
        return "parquet"
    return "csv"


def save_upload(up) -> str:
    """Persist an uploaded file to disk so DuckDB can stream it."""
    up.seek(0)
    digest = hashlib.md5(up.read(1 << 20)).hexdigest()[:12]
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(up.name))
    path = os.path.join(WORKDIR, f"{digest}_{up.size}_{safe}")
    if not os.path.exists(path):
        up.seek(0)
        with open(path + ".part", "wb") as fh:
            while chunk := up.read(64 << 20):
                fh.write(chunk)
        os.replace(path + ".part", path)
    return path


@st.cache_data(show_spinner=False)
def excel_sheets(path: str, mtime: float):
    return pd.ExcelFile(path).sheet_names


def dedupe(names):
    seen, out = {}, []
    for n in names:
        n = str(n).strip() or "column"
        if n in seen:
            seen[n] += 1
            n = f"{n}_{seen[n]}"
        else:
            seen[n] = 0
        out.append(n)
    return out


def load_table(table: str, path: str, opts: dict):
    kind = file_kind(path)
    c = con()
    if kind == "csv":
        args = [f"header={'true' if opts.get('header', True) else 'false'}"]
        if opts.get("delim"):
            delim = "\t" if opts["delim"] == "\\t" else opts["delim"]
            args.append(f"delim={ql(delim)}")
        if opts.get("all_text"):
            args.append("all_varchar=true")
        if opts.get("ignore_errors"):
            args.append("ignore_errors=true")
        if opts.get("full_scan"):
            args.append("sample_size=-1")
        if opts.get("encoding", "utf-8") != "utf-8":
            args.append(f"encoding={ql(opts['encoding'])}")
        return load_csv_robust(c, table, path, args, opts)
    elif kind == "parquet":
        c.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_parquet({ql(path)})")
    else:
        df = pd.read_excel(path, sheet_name=opts.get("sheet", 0),
                           dtype=str if opts.get("all_text") else None)
        df.columns = dedupe(df.columns)
        for col in df.columns:  # mixed-type columns -> text
            if df[col].dtype == object:
                df[col] = df[col].map(lambda x: x if pd.isna(x) else str(x))
        c.register("_excel_tmp", df)
        c.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _excel_tmp")
        c.unregister("_excel_tmp")
    bump_version()
    return []


CONVERT_ERR = re.compile(r'Error when converting column "(.+?)"')


def load_csv_robust(c, table: str, path: str, args: list, opts: dict) -> list:
    """Load a CSV, automatically fixing wrong type guesses.

    DuckDB guesses column types from a sample of rows. When a later row doesn't fit
    (e.g. a column guessed as Yes/No meets the text 'koi nhi'), that column is
    switched to text and the load is retried. Returns the columns read as text.
    """
    src = f"read_csv({ql(path)}, {', '.join(args)}"
    types: dict = {}
    if not opts.get("all_text"):
        # Yes/No/True/False columns -> keep as text: shows 'Yes'/'No' as written
        # and avoids the most common failure (free text further down the file).
        sniff = c.execute(f"DESCRIBE SELECT * FROM {src})").df()
        types = {n: "VARCHAR" for n, t in zip(sniff["column_name"], sniff["column_type"])
                 if t == "BOOLEAN"}
    auto_fixed: list = []
    full_scan = bool(opts.get("full_scan"))
    for _ in range(60):
        extra = ""
        if types:
            extra = ", types={" + ", ".join(f"{ql(k)}: 'VARCHAR'" for k in types) + "}"
        if full_scan and "sample_size=-1" not in args:
            extra += ", sample_size=-1"
        try:
            c.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM {src}{extra})")
            bump_version()
            return auto_fixed
        except duckdb.Error as e:
            m = CONVERT_ERR.search(str(e))
            if opts.get("all_text") or not m or m.group(1) in types:
                raise
            types[m.group(1)] = "VARCHAR"
            auto_fixed.append(m.group(1))
            # After the first surprise, scan the whole file for types so the
            # remaining columns are guessed correctly in one go.
            full_scan = True
    raise RuntimeError("Too many columns with inconsistent types - "
                       "tick 'Read all columns as text' and load again.")


def reset_widgets(prefix: str):
    for k in list(st.session_state.keys()):
        if k.startswith(prefix):
            del st.session_state[k]


def source_picker(prefix: str):
    """File uploader + read options. Returns (path, opts)."""
    path = None
    limit = st.get_option("server.maxUploadSize")
    if limit < UPLOAD_LIMIT_MB:
        st.warning(f"Upload limit is {limit} MB. To raise it: on your computer, start the app "
                   "with **run.bat / run.sh** or `python app.py`. On Streamlit Cloud, put "
                   "`.streamlit/config.toml` (from this project) at the **root of the GitHub "
                   "repo** and reboot the app.")
    up = st.file_uploader("Choose CSV / Excel / Parquet", type=FILE_TYPES, key=f"{prefix}_up")
    if up is not None:
        path = save_upload(up)

    opts = {"display_name": up.name if up is not None else None}
    if path and file_kind(path) == "excel":
        try:
            opts["sheet"] = st.selectbox("Sheet", excel_sheets(path, os.path.getmtime(path)),
                                         key=f"{prefix}_sheet")
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read workbook: {e}")
    with st.expander("Read options"):
        opts["all_text"] = st.checkbox(
            "Read all columns as text", key=f"{prefix}_alltext",
            help="Safest: keeps leading zeros / IDs as-is and avoids type errors. "
                 "Sum / Average still work (text is converted to numbers on the fly).")
        if not path or file_kind(path) == "csv":
            opts["header"] = st.checkbox("First row is header", True, key=f"{prefix}_header")
            opts["delim"] = st.text_input("Delimiter (blank = auto, \\t = tab)", "",
                                          key=f"{prefix}_delim")
            opts["encoding"] = st.selectbox("Encoding", ["utf-8", "latin-1", "utf-16"],
                                            key=f"{prefix}_enc")
            opts["ignore_errors"] = st.checkbox("Skip malformed rows", key=f"{prefix}_ign")
            opts["full_scan"] = st.checkbox(
                "Scan whole file to detect types (slower)", key=f"{prefix}_full",
                help="Use if loading fails with a type-conversion error.")
    return path, opts


def do_load(table: str, path: str, opts: dict, state_key: str, widget_prefix: str):
    t0 = time.time()
    try:
        with st.spinner(f"Loading {os.path.basename(path)} … (big files can take a minute)"):
            fixed = load_table(table, path, opts)
        st.session_state[f"{state_key}_fixed"] = fixed
        rows = con().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        st.session_state[state_key] = {"name": opts.get("display_name") or os.path.basename(path),
                                       "rows": rows,
                                       "secs": time.time() - t0}
        reset_widgets(widget_prefix)
        return True
    except Exception as e:  # noqa: BLE001
        st.error(f"Load failed: {e}")
        st.info("Tip: open **Read options** and tick *Read all columns as text* "
                "and/or *Skip malformed rows*, then load again.")
        return False


# ----------------------------------------------------------------------------
# Download helpers (files are generated only when the button is clicked)
# ----------------------------------------------------------------------------
def _download_accepts_callable() -> bool:
    """Newer Streamlit (>= ~1.50) can build a download only when it's clicked."""
    try:
        from streamlit.elements.widgets import button as _b
        return "Callable" in str(getattr(_b, "DownloadButtonDataType", ""))
    except Exception:  # noqa: BLE001
        return False


CALLABLE_DOWNLOADS = _download_accepts_callable()


def dl_button(container, label: str, make, file_name: str, key: str, mime=None, help=None):
    """Download button that builds the file only on demand, on any Streamlit version.

    New Streamlit: one click builds and downloads.
    Older Streamlit: a 'Prepare' click builds the file, then a download button appears.
    """
    if CALLABLE_DOWNLOADS:
        container.download_button(label, make, file_name, mime, key=key, help=help,
                                  **DL_IGNORE)
        return
    store = f"_dl_{key}"
    token = st.session_state.get("cache_token", "")
    ready = st.session_state.get(store)
    if ready and ready[0] == token and ready[1] == file_name:
        container.download_button(label, ready[2], file_name, mime, key=key, help=help)
    elif container.button(label.replace("⬇️", "⚙️ Prepare"), key=f"prep_{key}", help=help):
        with st.spinner("Preparing file…"):
            st.session_state[store] = (token, file_name, make())
        st.rerun()


def df_to_excel(df: pd.DataFrame, index=False) -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        df.to_excel(xw, index=index, sheet_name="Sheet1")
    return bio.getvalue()


def download_df(df: pd.DataFrame, name: str, key: str, index=False):
    c1, c2, _ = st.columns([1, 1, 4])
    dl_button(c1, "⬇️ CSV", lambda: df.to_csv(index=index).encode("utf-8-sig"),
              f"{name}.csv", f"dl_csv_{key}", "text/csv")
    if len(df) <= EXCEL_MAX_ROWS:
        dl_button(c2, "⬇️ Excel", lambda: df_to_excel(df, index), f"{name}.xlsx",
                  f"dl_xl_{key}")


def download_sql(sql: str, name: str, key: str, n_rows: int):
    """Download the full result of a (possibly huge) query, streamed via DuckDB."""
    def make_csv():
        out = os.path.join(WORKDIR, f"{name}_{int(time.time())}.csv")
        con().execute(f"COPY ({sql}) TO {ql(out)} (HEADER, DELIMITER ',')")
        with open(out, "rb") as fh:
            data = fh.read()
        os.remove(out)
        return data

    c1, c2, _ = st.columns([1, 1, 4])
    dl_button(c1, f"⬇️ CSV (all {n_rows:,} rows)", make_csv, f"{name}.csv",
              f"dlsql_csv_{key}", "text/csv")
    if n_rows <= EXCEL_MAX_ROWS:
        dl_button(c2, "⬇️ Excel", lambda: df_to_excel(con().execute(sql).df()),
                  f"{name}.xlsx", f"dlsql_xl_{key}",
                  help="Large Excel files can take a while to build; CSV is faster.")


# ----------------------------------------------------------------------------
# Filters
# ----------------------------------------------------------------------------
OPS = ["=", "≠", ">", "≥", "<", "≤", "contains", "does not contain", "starts with",
       "ends with", "in list (comma separated)", "not in list", "is blank", "is not blank"]
NO_VALUE_OPS = {"is blank", "is not blank"}


def build_condition(col: str, op: str, val: str, dtype: str):
    c = qi(col)
    txt = f"CAST({c} AS VARCHAR)"
    if op == "is blank":
        return f"({c} IS NULL OR TRIM({txt}) = '')"
    if op == "is not blank":
        return f"({c} IS NOT NULL AND TRIM({txt}) <> '')"
    if val == "":
        return None
    low = f"lower({txt})"
    v = ql(val.lower())
    if op == "contains":
        return f"contains({low}, {v})"
    if op == "does not contain":
        return f"NOT coalesce(contains({low}, {v}), false)"
    if op == "starts with":
        return f"starts_with({low}, {v})"
    if op == "ends with":
        return f"suffix({low}, {v})"
    if op in ("in list (comma separated)", "not in list"):
        items = [x.strip() for x in val.split(",") if x.strip()]
        if not items:
            return None
        cond = f"TRIM({txt}) IN ({', '.join(ql(x) for x in items)})"
        return cond if op.startswith("in") else f"NOT coalesce({cond}, false)"
    sym = {"=": "=", "≠": "<>", ">": ">", "≥": ">=", "<": "<", "≤": "<="}[op]
    return f"{c} {sym} CAST({ql(val)} AS {dtype})"


def filter_sidebar(cols: dict) -> str:
    st.subheader("🔎 Filters")
    st.caption("Applied to every tab.")
    n = st.number_input("Number of filters", 0, 15, 0, key="w_nfilters")
    conds = []
    for i in range(int(n)):
        with st.container(border=True):
            col = st.selectbox("Column", list(cols), key=f"w_fcol_{i}")
            op = st.selectbox("Condition", OPS, key=f"w_fop_{i}")
            val = "" if op in NO_VALUE_OPS else st.text_input("Value", key=f"w_fval_{i}")
            cond = build_condition(col, op, val, cols[col])
            if cond:
                conds.append(cond)
    logic = " AND "
    if len(conds) > 1:
        logic = " AND " if st.radio("Combine filters with", ["AND", "OR"], horizontal=True,
                                    key="w_flogic") == "AND" else " OR "
    with st.expander("Advanced: SQL WHERE clause"):
        adv = st.text_area("e.g.  \"Amount\" > 1000 AND \"State\" = 'MH'", key="w_fadv").strip()
    where = logic.join(f"({c})" for c in conds)
    if adv:
        where = f"({where}) AND ({adv})" if where else f"({adv})"
    return where


# ----------------------------------------------------------------------------
# Sidebar: load main data
# ----------------------------------------------------------------------------
with st.sidebar:
    st.title("📊 Big CSV Explorer")
    st.caption("Value counts · Pivots · Filters — for files of any size")
    path, opts = source_picker("main")
    if path and st.button("📂 Load data", type="primary", **FULL_BTN):
        do_load("data", path, opts, "main_info", "w_")

info = st.session_state.get("main_info")
if not info or not table_exists("data"):
    hero("📊 Big CSV Explorer", "Value counts, pivots and filters for files of any size")
    st.markdown(
        """
**Upload a file from the sidebar and click *Load data* to begin.**

- Works with **CSV / TXT / TSV / Excel / Parquet**, tested with 10 crore rows.
- Then use the tabs: **Overview · Value Counts · Pivot · SQL**.
- Sidebar **Filters** apply to all tabs.
"""
    )
    st.stop()

cols = columns_of("data")
with st.sidebar:
    st.divider()
    where = filter_sidebar(cols)

try:
    con().execute("CREATE OR REPLACE VIEW filtered AS SELECT * FROM data"
                  + (f" WHERE {where}" if where else ""))
    filtered_rows = con().execute("SELECT COUNT(*) FROM filtered").fetchone()[0]
except Exception as e:  # noqa: BLE001
    st.sidebar.error(f"Filter error: {e}")
    con().execute("CREATE OR REPLACE VIEW filtered AS SELECT * FROM data")
    where, filtered_rows = "", info["rows"]

st.session_state["cache_token"] = f"{get_engine()['version']}|{where}"
total_rows = con().execute("SELECT COUNT(*) FROM data").fetchone()[0]

# Header
hero("📊 Big CSV Explorer", f"Exploring <b>{info['name']}</b>")
h1, h2, h3, h4 = st.columns(4)
h1.metric("Total rows", f"{total_rows:,}")
h2.metric("Rows after filters", f"{filtered_rows:,}",
          delta=None if not where else f"{filtered_rows / max(total_rows, 1):.1%} of total",
          delta_color="off")
h3.metric("Columns", len(cols))
h4.metric("Load time", f"{info.get('secs', 0):.1f} s")
if st.session_state.get("main_info_fixed"):
    fx = st.session_state["main_info_fixed"]
    st.info(f"Auto-fixed {len(fx)} column(s) whose values didn't match the guessed type; "
            f"they were read as text: {', '.join(fx)}")

tab_over, tab_vc, tab_pv, tab_sql = st.tabs(
    ["📋 Overview", "🔢 Value Counts", "📊 Pivot", "🧮 SQL"])

# ----------------------------------------------------------------------------
# Overview
# ----------------------------------------------------------------------------
with tab_over:
    st.subheader("Preview")
    n_prev = st.select_slider("Rows to preview", [10, 50, 100, 500, 1000, 5000], 100, key="w_prev")
    st.dataframe(query(f"SELECT * FROM filtered LIMIT {n_prev}"), **FULL_DF)

    st.subheader("Column summary")
    if st.toggle("Compute summary (nulls, unique, min, max, mean …)", key="w_summ"):
        with st.spinner("Summarising…"):
            s = query("SUMMARIZE filtered")
        keep = [c for c in ["column_name", "column_type", "count", "null_percentage",
                            "approx_unique", "min", "max", "avg", "std", "q25", "q50", "q75"]
                if c in s.columns]
        s = s[keep].rename(columns={"column_name": "Column", "column_type": "Type",
                                    "count": "Rows", "null_percentage": "Null %",
                                    "approx_unique": "Unique (approx)", "q50": "median"})
        st.dataframe(s, **FULL_DF, hide_index=True)
        download_df(s, "column_summary", "summ")
    else:
        st.dataframe(pd.DataFrame({"Column": list(cols), "Type": list(cols.values())}),
                     hide_index=True, **FULL_DF)

# ----------------------------------------------------------------------------
# Value counts
# ----------------------------------------------------------------------------
def value_count_sql(sel_cols, include_blank, normalize, sort, top_n):
    exprs = []
    for c in sel_cols:
        e = qi(c)
        if normalize:
            e = f"NULLIF(UPPER(TRIM(CAST({e} AS VARCHAR))), '')"
        exprs.append(f"{e} AS {qi(c)}")
    where_nb = "" if include_blank else (
        " WHERE " + " AND ".join(f"{qi(c)} IS NOT NULL" for c in sel_cols))
    keys = ", ".join(qi(c) for c in sel_cols)
    order = {"Count ↓": f'"Count" DESC, {keys}', "Count ↑": f'"Count" ASC, {keys}',
             "Value ↑": f"{keys} ASC NULLS LAST", "Value ↓": f"{keys} DESC NULLS LAST"}[sort]
    group = ", ".join(str(i + 1) for i in range(len(sel_cols)))
    limit = f" LIMIT {int(top_n)}" if top_n else ""
    return (f'SELECT {", ".join(exprs)}, COUNT(*) AS "Count", '
            f'100.0 * COUNT(*) / SUM(COUNT(*)) OVER () AS "Percent", '
            f'COUNT(*) OVER () AS "__groups", SUM(COUNT(*)) OVER () AS "__total" '
            f'FROM filtered{where_nb} GROUP BY {group} ORDER BY {order}{limit}')


with tab_vc:
    st.subheader("Value counts")
    sel = st.multiselect("Column(s) — pick several for combination counts", list(cols),
                         key="w_vc_cols")
    c1, c2, c3, c4 = st.columns(4)
    top_n = c1.number_input("Top N (0 = all)", 0, 10_000_000, 100, step=50, key="w_vc_top")
    sort = c2.selectbox("Sort by", ["Count ↓", "Count ↑", "Value ↑", "Value ↓"], key="w_vc_sort")
    inc_blank = c3.checkbox("Include blanks / NULL", True, key="w_vc_blank")
    norm = c4.checkbox("Ignore case & extra spaces", False, key="w_vc_norm")

    if sel:
        vc = query(value_count_sql(sel, inc_blank, norm, sort, top_n))
        groups = int(vc["__groups"].iat[0]) if len(vc) else 0
        considered = int(vc["__total"].iat[0]) if len(vc) else 0
        vc = vc.drop(columns=["__groups", "__total"])
        vc["Cumulative %"] = vc["Percent"].cumsum()
        m1, m2, m3 = st.columns(3)
        m1.metric("Rows counted", f"{considered:,}")
        m2.metric("Unique values" if len(sel) == 1 else "Unique combinations", f"{groups:,}")
        m3.metric("Shown", f"{len(vc):,}")

        left, right = st.columns([3, 2]) if len(sel) == 1 else (st.container(), None)
        with left:
            st.dataframe(
                vc, **FULL_DF, hide_index=True, height=480,
                column_config={
                    "Count": st.column_config.NumberColumn(format="localized"),
                    "Percent": st.column_config.ProgressColumn(format="%.2f%%", min_value=0,
                                                               max_value=100),
                    "Cumulative %": st.column_config.NumberColumn(format="%.2f%%"),
                })
        if right is not None and len(vc):
            # The chart is optional: a broken/incompatible charting library must
            # never stop the rest of the app (Pivot, SQL) from working.
            try:
                import altair as alt
                chart_df = vc.head(25).assign(Value=lambda d: d[sel[0]].astype(str))
                right.altair_chart(
                    alt.Chart(chart_df).mark_bar(color="#6E5CE6", cornerRadiusEnd=4).encode(
                        x="Count:Q", y=alt.Y("Value:N", sort="-x", title=sel[0]),
                        tooltip=["Value", "Count", alt.Tooltip("Percent:Q", format=".2f")]),
                    **FULL_CHART)
            except Exception:  # noqa: BLE001
                right.caption("Chart unavailable (charting library 'altair' failed to load). "
                              "Fix with:  pip install -U altair")
        download_df(vc, "value_counts_" + "_".join(sel)[:50], "vc")

    st.divider()
    with st.expander("📑 Value counts for **every** column → one Excel workbook"):
        top_all = st.number_input("Top N per column", 1, 100_000, 1000, key="w_vc_alltop")

        def all_counts_xlsx():
            bio = io.BytesIO()
            used = set()
            with pd.ExcelWriter(bio, engine="openpyxl") as xw:
                for col in cols:
                    d = con().execute(value_count_sql([col], True, False, "Count ↓",
                                                      top_all)).df()
                    d = d.drop(columns=["__groups", "__total"])
                    name = re.sub(r"[\[\]:*?/\\]", "_", str(col))[:28] or "col"
                    base, k = name, 1
                    while name.lower() in used:
                        name, k = f"{base[:25]}_{k}", k + 1
                    used.add(name.lower())
                    d.to_excel(xw, sheet_name=name, index=False)
            return bio.getvalue()

        dl_button(st, "⬇️ Build & download workbook", all_counts_xlsx,
                  "value_counts_all_columns.xlsx", "dl_vc_all")

# ----------------------------------------------------------------------------
# Pivot
# ----------------------------------------------------------------------------
AGGS = {
    "Count": "COUNT({c})",
    "Count distinct": "COUNT(DISTINCT {c})",
    "Sum": "SUM({n})",
    "Average": "AVG({n})",
    "Min": "MIN({c})",
    "Max": "MAX({c})",
    "Median": "MEDIAN({n})",
    "Std dev": "STDDEV_SAMP({n})",
}


def agg_expr(agg: str, col, extra_filter: str = "") -> str:
    if col is None:
        e = "COUNT(*)"
    else:
        c = qi(col)
        n = c if is_numeric(cols[col]) else f"TRY_CAST({c} AS DOUBLE)"
        e = AGGS[agg].format(c=c, n=n)
    return f"{e} FILTER (WHERE {extra_filter})" if extra_filter else e


with tab_pv:
    st.subheader("Pivot table")
    p1, p2 = st.columns(2)
    rows = p1.multiselect("Rows", list(cols), key="w_pv_rows")
    colf = p2.selectbox("Columns (optional)", ["(none)"] + [c for c in cols if c not in rows],
                        key="w_pv_col")
    colf = None if colf == "(none)" else colf
    p3, p4 = st.columns(2)
    vals = p3.multiselect("Values (blank = count of rows)", list(cols), key="w_pv_vals")
    aggs = p4.multiselect("Aggregation", list(AGGS), default=["Sum"], key="w_pv_aggs") \
        if vals else []
    o1, o2, o3, o4 = st.columns(4)
    show_totals = o1.checkbox("Grand totals", True, key="w_pv_tot")
    subtotals = o2.checkbox("Subtotals", False, key="w_pv_sub", disabled=len(rows) < 2)
    sort_by = o3.selectbox("Sort rows by", ["Row labels", "Total ↓", "Total ↑"], key="w_pv_sort")
    measures = [(f"{a} of {v}", a, v) for v in vals for a in aggs] if vals \
        else [("Count of rows", "Count", None)]
    pct_ok = len(measures) == 1 and measures[0][1] in ("Count", "Sum")
    show_as = o4.selectbox("Show values as", ["Values", "% of grand total", "% of row total",
                                              "% of column total"],
                           key="w_pv_pct", disabled=not pct_ok,
                           help="Available for a single Count or Sum measure.")
    if not pct_ok:
        show_as = "Values"

    if vals and not aggs:
        st.info("Pick at least one aggregation.")
    elif rows or colf:
        try:
            # --- column field values
            col_vals = []
            if colf:
                n_distinct = scalar(f"SELECT COUNT(DISTINCT {qi(colf)}) FROM filtered")
                if n_distinct > MAX_PIVOT_COLUMNS:
                    raise ValueError(f"'{colf}' has {n_distinct:,} distinct values — too many "
                                     f"for pivot columns (max {MAX_PIVOT_COLUMNS}). "
                                     f"Move it to Rows instead.")
                col_vals = query(f"SELECT CAST({qi(colf)} AS VARCHAR) AS v FROM filtered "
                                 f"GROUP BY {qi(colf)} ORDER BY {qi(colf)} NULLS LAST")["v"].tolist()

            need_totals = show_totals or show_as != "Values"
            select_parts, out_names = [], []
            for mname, agg, vcol in measures:
                for v in col_vals:
                    cond = (f"{qi(colf)} IS NULL" if v is None
                            else f"CAST({qi(colf)} AS VARCHAR) = {ql(v)}")
                    label = "(blank)" if v is None else str(v)
                    name = label if len(measures) == 1 else f"{mname} | {label}"
                    select_parts.append(f"{agg_expr(agg, vcol, cond)} AS {qi(name)}")
                    out_names.append(name)
                if not colf or need_totals:
                    name = mname if not colf else (
                        "Grand Total" if len(measures) == 1 else f"{mname} | Grand Total")
                    select_parts.append(f"{agg_expr(agg, vcol)} AS {qi(name)}")
                    out_names.append(name)
            total_col = out_names[-1] if (not colf or need_totals) else None

            row_keys = ", ".join(qi(r) for r in rows)
            grp_flags = ", ".join(f"GROUPING({qi(r)}) AS {qi('__g' + str(i))}"
                                  for i, r in enumerate(rows))
            if rows:
                if subtotals and len(rows) > 1:
                    group_by = f"GROUP BY ROLLUP ({row_keys})"
                elif need_totals:
                    group_by = f"GROUP BY GROUPING SETS (({row_keys}), ())"
                else:
                    group_by = f"GROUP BY {row_keys}"
                if sort_by == "Row labels" or not total_col or subtotals:
                    order = ", ".join(f"{qi('__g' + str(i))}, {qi(r)} NULLS LAST"
                                      for i, r in enumerate(rows))
                else:
                    direction = "DESC" if sort_by == "Total ↓" else "ASC"
                    order = f"{qi('__g0')}, {qi(total_col)} {direction}"
                sql = (f"SELECT {row_keys}, {grp_flags}, {', '.join(select_parts)} "
                       f"FROM filtered {group_by} ORDER BY {order}")
            else:
                sql = f"SELECT {', '.join(select_parts)} FROM filtered"

            pv = query(sql).copy()

            # --- labels for blanks / totals
            if rows:
                for i, r in enumerate(rows):
                    pv[r] = pv[r].astype(object).where(pv[r].notna(), "(blank)")
                for i in range(len(rows) - 1, -1, -1):
                    g = pv[f"__g{i}"] == 1
                    if i == 0:
                        pv.loc[g, rows[0]] = "Grand Total"
                    else:
                        pv.loc[g, rows[i]] = "Total"
                    for j in range(i + 1, len(rows)):
                        pv.loc[g, rows[j]] = ""
                pv = pv.drop(columns=[f"__g{i}" for i in range(len(rows))])

            # --- show values as %
            value_cols = [c for c in out_names]
            if show_as != "Values":
                num = pv[value_cols].astype(float)
                if show_as == "% of grand total":
                    grand = float(num[total_col].iloc[-1]) if rows else float(num[total_col].iloc[0])
                    num = num / grand * 100
                elif show_as == "% of row total":
                    num = num.div(num[total_col], axis=0) * 100
                else:  # column total = grand total row (last row)
                    num = num.div(num.iloc[-1], axis=1) * 100
                pv[value_cols] = num
                if not show_totals:  # totals were only needed for the maths
                    pv = pv.drop(columns=[total_col]) if colf else pv
                    if rows:
                        pv = pv[pv[rows[0]] != "Grand Total"]

            n_out = len(pv)
            st.caption(f"{n_out:,} rows × {len(pv.columns):,} columns"
                       + (f" — showing first {PREVIEW_ROWS:,}" if n_out > PREVIEW_ROWS else ""))
            fmt = "%.2f%%" if show_as != "Values" else "localized"
            st.dataframe(pv.head(PREVIEW_ROWS), **FULL_DF, hide_index=True,
                         height=520,
                         column_config={c: st.column_config.NumberColumn(format=fmt)
                                        for c in value_cols if c in pv.columns})
            download_df(pv, "pivot", "pv")
            with st.expander("Show SQL"):
                st.code(sql, language="sql")
        except Exception as e:  # noqa: BLE001
            st.error(f"Pivot failed: {e}")
    else:
        st.info("Pick at least one Rows or Columns field.")

# ----------------------------------------------------------------------------
# SQL
# ----------------------------------------------------------------------------
with tab_sql:
    st.subheader("Custom SQL (DuckDB)")
    st.caption("Tables: `data` (full file), `filtered` (after sidebar filters). "
               "Quote column names with double quotes.")
    sample_col = qi(next(iter(cols)))
    sql_txt = st.text_area(
        "Query", height=160, key="sql_box",
        value=f"SELECT {sample_col}, COUNT(*) AS n\nFROM filtered\nGROUP BY 1\nORDER BY n DESC\nLIMIT 100")
    if st.button("▶️ Run", type="primary", key="sql_run"):
        st.session_state["sql_last"] = sql_txt
    if st.session_state.get("sql_last"):
        q_ = st.session_state["sql_last"].strip().rstrip(";")
        try:
            n = scalar(f"SELECT COUNT(*) FROM ({q_})")
            st.caption(f"{n:,} rows" + (f" — showing first {PREVIEW_ROWS:,}" if n > PREVIEW_ROWS else ""))
            st.dataframe(query(f"SELECT * FROM ({q_}) LIMIT {PREVIEW_ROWS}"),
                         **FULL_DF)
            download_sql(q_, "sql_result", "sql", n)
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
