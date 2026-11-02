# Big CSV Explorer

Use this tool for **value counts, pivots and filters** on CSV, Excel and Parquet files of any size.
It has been tested on 10 crore rows (a 3.9 GB CSV):

| Step | Time |
|---|---|
| Load | ~20 s |
| Value counts | ~0.5 s |
| Pivot | ~1.3 s |

## Run
- **Windows:** double-click `run.bat`
- **Mac/Linux:** `./run.sh`
- **Or from any folder:** `python app.py`

Each of these starts the tool in your browser with **no file-size limit** (100 GB) and the app's *Indigo Mist* theme.
Plain `streamlit run app.py` also works from inside this folder.

## How to use
1. In the sidebar, **upload** your CSV / Excel / Parquet file.
2. Click **📂 Load data**.
3. Use the tabs:

| Tab | What it does |
|---|---|
| **Sidebar filters** | Up to 15 filters, combined with AND or OR (=, ≠, >, <, contains, starts/ends with, in list, is blank …). There's also a raw SQL WHERE box. Filters apply to every tab. |
| **Overview** | Shows preview rows and a column summary: type, % blank, number of unique values, min/max/mean/quartiles. |
| **Value Counts** | Shows count, % and cumulative % for one or more columns. Options: Top-N, sorting, including or leaving out blanks, ignoring case and spaces. A bar chart is included. You can also export one Excel workbook with value counts for **every** column. |
| **Pivot** | Rows × Columns × Values, using Count / Count distinct / Sum / Average / Min / Max / Median / Std dev. Options: grand totals, subtotals, sort by total, and % of grand/row/column total. |
| **SQL** | Write your own DuckDB SQL over `data` (the whole file) or `filtered` (rows left after the sidebar filters). |

Every result can be downloaded as CSV or Excel.

## Tips
- **Columns with mixed values load on their own.** If a column has values that don't fit its guessed type (for example, text in a Yes/No column), that column is switched to text automatically.
- **If a load still fails:** open **Read options** and tick *Read all columns as text* and/or *Skip malformed rows*.
- **To keep leading zeros in IDs:** tick *Read all columns as text*.
- **Very large uploads:** multi-GB files take a while to upload through the browser. Analysis is fast once the file is loaded.
- **The bar chart is optional.** If the `altair` library fails to load, everything else still works. To fix the chart, run `pip install -U altair`.
- **Disk space:** keep free space of about 25% of the CSV's size.
- **Older Streamlit:** on older versions, downloads need two clicks (Prepare, then Download). Run `pip install -U streamlit` for one-click downloads.

## Deploying / sharing
**Vercel and Netlify won't work.** They're serverless, and Streamlit needs a server that stays running.

**Share from your own computer** (data stays on your machine). Start the app with this command:
```
python app.py --server.address=0.0.0.0
```
Colleagues on the same Wi-Fi/LAN then open `http://<your-computer-IP>:8501`.

**Hugging Face Spaces** (free; 16 GB RAM, good for big files):
1. Create a new Space and choose the **Docker** SDK (blank template).
2. Upload all files from this folder. That includes `Dockerfile` and the `.streamlit` folder.
3. Wait for the build. The app runs on port 7860.
4. Make the Space **Private** if your data is sensitive.

**Render / Railway / Fly.io:** create a service from this folder. Each one detects the `Dockerfile` automatically.
Pick a plan with enough RAM, about 2–4 GB for crore-row files.

**Streamlit Community Cloud** (free, easiest, but only ~1 GB RAM, so it suits smaller files):
1. Push this folder to GitHub with `app.py` at the repo root.
2. Go to share.streamlit.io → New app → choose the repo → main file `app.py`.
