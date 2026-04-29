# LILA BLACK — Level Designer Visualization Tool

A web-based tool for Level Designers to explore player behavior, kill zones, movement patterns, and loot distribution across LILA BLACK's three maps.

**Live demo:** _[add your Streamlit Community Cloud URL here after deploying]_

---

## What it does

- **Map view** — plots all event types (kills, deaths, loot, storm deaths) as distinct markers over the correct minimap, with human vs bot events visually separated
- **Heatmap overlays** — toggle between traffic density, kill zones, death zones, and loot concentration
- **Match playback** — animated timeline to watch a match unfold event by event
- **Player stats** — per-player kill/death/loot breakdown and distribution charts
- **Filters** — filter by map, date, and match ID from the sidebar

---

## Running locally

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Place your data files
#    data/February_10/<user_id>_<match_id>.nakama-0
#    data/February_11/...
#    minimaps/AmbroseValley_Minimap.png
#    minimaps/GrandRift_Minimap.png
#    minimaps/Lockdown_Minimap.jpg

# 3. Run
streamlit run app.py
```

To generate sample data for testing (without the real dataset):
```bash
python generate_sample_data.py
```

---

## Deploying to Streamlit Community Cloud

1. Push this repo to GitHub (public or private)
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app
3. Connect your GitHub repo, set `app.py` as the entrypoint
4. Click Deploy — you get a shareable `https://your-app.streamlit.app` URL

> **Note on data:** The real parquet files are large. Either commit them to the repo (if under 100MB total) or use `st.secrets` + cloud storage (S3/GCS) for production.

---

## Project structure

```
lila_black/
├── app.py                    # Main Streamlit application
├── generate_sample_data.py   # Generates realistic sample data for testing
├── requirements.txt
├── .streamlit/
│   └── config.toml           # Dark theme config
├── data/
│   ├── February_10/          # Parquet files
│   ├── February_11/
│   ├── February_12/
│   ├── February_13/
│   └── February_14/
└── minimaps/
    ├── AmbroseValley_Minimap.png
    ├── GrandRift_Minimap.png
    └── Lockdown_Minimap.jpg
```

---

## Technical decisions

| Decision | Choice | Why |
|---|---|---|
| Framework | Streamlit | Fastest path to a hosted, interactive tool in Python |
| Charting | Plotly | Built-in animation support for timeline playback; scatter + contour in one lib |
| Coordinate transform | Per-map scale + origin | Directly from README spec; Y=elevation ignored |
| Heatmap | Histogram2dContour | Smooth density rendering without needing raw pixel arrays |
| Data loading | Cached via `@st.cache_data` | Avoids re-loading 1M+ rows on every interaction |
| Bot detection | UUID regex on `user_id` | Deterministic, O(1) per row |
