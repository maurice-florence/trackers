# Fitbit Analytics — Streamlit Blueprint

This minimal Streamlit app skeleton implements the design spec for local Fitbit Google Takeout analysis.

Quick start

1. Create a virtual environment and install requirements:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r fitbit-analytics\requirements.txt
```

2. Run the app:

```bash
streamlit run fitbit-analytics\app.py
```

Notes

- The loader expects a local path (default `G:\Mijn Drive\Data Analyse\00_DATA-Life_Analysis\fitbit-data`).
- If no files are present, the app will show informational messages. The modules are intentionally minimal and designed to be extended.
