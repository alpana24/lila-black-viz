import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from PIL import Image
import os
import glob
import re
from pathlib import Path

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LILA BLACK — Level Designer Tool",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Map constants ─────────────────────────────────────────────────────────────
MAP_CONFIG = {
    "AmbroseValley": {"scale": 900,  "origin_x": -370, "origin_z": -473},
    "GrandRift":     {"scale": 581,  "origin_x": -290, "origin_z": -290},
    "Lockdown":      {"scale": 1000, "origin_x": -500, "origin_z": -500},
}
MINIMAP_SIZE = 1024

EVENT_COLORS = {
    "Kill":           "#FF4444",
    "Killed":         "#FF8C00",
    "BotKill":        "#FF7777",
    "BotKilled":      "#FFB347",
    "KilledByStorm":  "#AA44FF",
    "Loot":           "#44FF88",
    "Position":       "#4488FF",
    "BotPosition":    "#44CCFF",
}

EVENT_SYMBOLS = {
    "Kill":           "star",
    "Killed":         "x",
    "BotKill":        "star-triangle-up",
    "BotKilled":      "x-thin",
    "KilledByStorm":  "diamond",
    "Loot":           "circle",
    "Position":       "circle-open",
    "BotPosition":    "circle-open",
}

EVENT_LABELS = {
    "Kill":           "Player Kill",
    "Killed":         "Player Death",
    "BotKill":        "Bot Kill",
    "BotKilled":      "Death by Bot",
    "KilledByStorm":  "Storm Death",
    "Loot":           "Loot Pickup",
    "Position":       "Player Position",
    "BotPosition":    "Bot Position",
}

HUMAN_EVENTS  = {"Kill", "Killed", "KilledByStorm", "Loot", "Position"}
BOT_EVENTS    = {"BotKill", "BotKilled", "BotPosition"}
COMBAT_EVENTS = {"Kill", "Killed", "BotKill", "BotKilled", "KilledByStorm"}

# ── Data helpers ──────────────────────────────────────────────────────────────
def is_human(user_id: str) -> bool:
    """UUID = human, short numeric = bot."""
    return bool(re.match(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        str(user_id), re.IGNORECASE
    ))

def world_to_pixel(x, z, map_id):
    cfg = MAP_CONFIG[map_id]
    u = (x - cfg["origin_x"]) / cfg["scale"]
    v = (z - cfg["origin_z"]) / cfg["scale"]
    px = u * MINIMAP_SIZE
    py = (1 - v) * MINIMAP_SIZE
    return px, py

@st.cache_data(show_spinner=False)
def load_data(data_dir: str) -> pd.DataFrame:
    """Load all parquet files from all day subfolders."""
    frames = []
    day_folders = sorted(glob.glob(os.path.join(data_dir, "February_*")))

    if not day_folders:
        # Try loading directly from data_dir
        day_folders = [data_dir]

    for folder in day_folders:
        date_label = os.path.basename(folder)
        files = [f for f in glob.glob(os.path.join(folder, "*"))
                 if os.path.isfile(f)]
        for fpath in files:
            fname = os.path.basename(fpath)
            try:
                df = pd.read_parquet(fpath)
                # Decode event bytes
                if df['event'].dtype == object:
                    df['event'] = df['event'].apply(
                        lambda e: e.decode('utf-8') if isinstance(e, bytes) else str(e)
                    )
                df['date'] = date_label
                # Parse user/match from filename
                parts = fname.split('_', 1)
                if len(parts) >= 1:
                    df['file_user_id'] = parts[0]
                frames.append(df)
            except Exception:
                continue

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)

    # Clean match_id (strip .nakama-0 suffix for display)
    if 'match_id' in out.columns:
        out['match_id_clean'] = out['match_id'].str.replace(r'\.nakama-\d+$', '', regex=True)
    else:
        out['match_id_clean'] = 'unknown'

    # Is human flag
    out['is_human'] = out['user_id'].apply(lambda x: is_human(str(x)))

    # Coordinate transform per map
    out['px'] = np.nan
    out['py'] = np.nan
    for map_id in MAP_CONFIG:
        mask = out['map_id'] == map_id
        if mask.any():
            px, py = world_to_pixel(out.loc[mask, 'x'], out.loc[mask, 'z'], map_id)
            out.loc[mask, 'px'] = px
            out.loc[mask, 'py'] = py

    # Normalise timestamp to seconds within match
    if 'ts' in out.columns:
        out['ts'] = pd.to_datetime(out['ts'], errors='coerce')
        out['ts_ms'] = out['ts'].astype('int64') // 1_000_000
        # Per-match relative time in seconds
        min_ts = out.groupby('match_id_clean')['ts_ms'].transform('min')
        out['ts_rel'] = (out['ts_ms'] - min_ts) / 1000

    return out

def load_minimap(map_id: str, minimap_dir: str):
    """Try to load minimap image, return PIL Image or None."""
    ext_map = {
        "AmbroseValley": ["AmbroseValley_Minimap.png", "AmbroseValley_Minimap.jpg"],
        "GrandRift":     ["GrandRift_Minimap.png", "GrandRift_Minimap.jpg"],
        "Lockdown":      ["Lockdown_Minimap.jpg", "Lockdown_Minimap.png"],
    }
    for fname in ext_map.get(map_id, []):
        fpath = os.path.join(minimap_dir, fname)
        if os.path.exists(fpath):
            return Image.open(fpath).convert("RGBA")
    return None

def make_placeholder_map(map_id: str) -> Image.Image:
    """Generate a simple placeholder if minimap not found."""
    bg_colors = {
        "AmbroseValley": (34, 45, 30, 255),
        "GrandRift":     (30, 35, 50, 255),
        "Lockdown":      (40, 35, 30, 255),
    }
    arr = np.full((MINIMAP_SIZE, MINIMAP_SIZE, 4), bg_colors.get(map_id, (40,40,40,255)), dtype=np.uint8)
    return Image.fromarray(arr, 'RGBA')

# ── Plotting helpers ──────────────────────────────────────────────────────────
def build_figure(df_plot: pd.DataFrame, map_id: str, minimap_dir: str,
                 show_events: list, overlay_mode: str,
                 heatmap_bins: int = 60) -> go.Figure:

    img = load_minimap(map_id, minimap_dir) or make_placeholder_map(map_id)
    W, H = img.size

    fig = go.Figure()

    # Background minimap image
    import base64, io
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()

    fig.add_layout_image(
        dict(
            source=f"data:image/png;base64,{b64}",
            xref="x", yref="y",
            x=0, y=0,
            sizex=W, sizey=H,
            sizing="stretch",
            opacity=1.0,
            layer="below"
        )
    )

    if df_plot.empty:
        _set_axes(fig, W, H)
        return fig

    # ── Heatmap overlay ────────────────────────────────────────────────────────
    if overlay_mode != "None":
        if overlay_mode == "Traffic (all positions)":
            hm_df = df_plot[df_plot['event'].isin({"Position", "BotPosition"})]
        elif overlay_mode == "Kill zones":
            hm_df = df_plot[df_plot['event'].isin({"Kill", "BotKill"})]
        elif overlay_mode == "Death zones":
            hm_df = df_plot[df_plot['event'].isin({"Killed", "BotKilled", "KilledByStorm"})]
        elif overlay_mode == "Loot zones":
            hm_df = df_plot[df_plot['event'] == "Loot"]
        else:
            hm_df = pd.DataFrame()

        if not hm_df.empty and hm_df['px'].notna().any():
            hm_data = hm_df.dropna(subset=['px', 'py'])
            fig.add_trace(go.Histogram2dContour(
                x=hm_data['px'],
                y=hm_data['py'],
                colorscale="Hot",
                reversescale=True,
                showscale=False,
                opacity=0.55,
                nbinsx=heatmap_bins,
                nbinsy=heatmap_bins,
                contours=dict(showlines=False),
                name=overlay_mode,
                hoverinfo="skip",
            ))

    # ── Event scatter markers ──────────────────────────────────────────────────
    for event in show_events:
        sub = df_plot[df_plot['event'] == event].dropna(subset=['px', 'py'])
        if sub.empty:
            continue
        # Limit position dots to sample for performance
        if event in {"Position", "BotPosition"} and len(sub) > 3000:
            sub = sub.sample(3000, random_state=42)

        hover = sub.apply(
            lambda r: (
                f"<b>{EVENT_LABELS.get(r['event'], r['event'])}</b><br>"
                f"Player: {str(r['user_id'])[:12]}…<br>"
                f"Map: {r.get('map_id','')}<br>"
                f"Time: {r.get('ts_rel', 0):.1f}s"
            ), axis=1
        )

        fig.add_trace(go.Scatter(
            x=sub['px'],
            y=sub['py'],
            mode='markers',
            marker=dict(
                color=EVENT_COLORS.get(event, "#FFFFFF"),
                symbol=EVENT_SYMBOLS.get(event, "circle"),
                size=10 if event not in {"Position", "BotPosition"} else 4,
                opacity=0.85 if event not in {"Position", "BotPosition"} else 0.35,
                line=dict(width=1, color="rgba(0,0,0,0.4)")
                    if event not in {"Position", "BotPosition"} else dict(width=0),
            ),
            name=EVENT_LABELS.get(event, event),
            text=hover,
            hovertemplate="%{text}<extra></extra>",
            customdata=sub['ts_rel'].fillna(0).values,
        ))

    _set_axes(fig, W, H)
    return fig


def build_timeline_figure(df_match: pd.DataFrame, map_id: str, minimap_dir: str,
                           show_events: list, max_time: float) -> go.Figure:
    """Animated playback figure with time slider."""
    img = load_minimap(map_id, minimap_dir) or make_placeholder_map(map_id)
    W, H = img.size
    import base64, io
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()

    # Build frames at 10-second intervals
    step = max(10, int(max_time / 40))
    time_steps = list(range(0, int(max_time) + step, step))

    frames = []
    for t in time_steps:
        window = df_match[
            (df_match['ts_rel'] <= t) &
            (df_match['event'].isin(show_events))
        ].dropna(subset=['px', 'py'])

        traces = []
        for event in show_events:
            sub = window[window['event'] == event]
            if sub.empty:
                traces.append(go.Scatter(x=[], y=[], mode='markers',
                                         name=EVENT_LABELS.get(event, event)))
                continue
            if event in {"Position", "BotPosition"} and len(sub) > 1500:
                sub = sub.sample(1500, random_state=42)
            traces.append(go.Scatter(
                x=sub['px'], y=sub['py'],
                mode='markers',
                marker=dict(
                    color=EVENT_COLORS.get(event, "#FFF"),
                    symbol=EVENT_SYMBOLS.get(event, "circle"),
                    size=10 if event not in {"Position", "BotPosition"} else 4,
                    opacity=0.85 if event not in {"Position", "BotPosition"} else 0.4,
                ),
                name=EVENT_LABELS.get(event, event),
                showlegend=(t == time_steps[0]),
            ))
        frames.append(go.Frame(data=traces, name=str(t),
                               layout=go.Layout(title_text=f"T = {t}s")))

    # Initial data (first frame)
    init_window = df_match[
        (df_match['ts_rel'] <= time_steps[0]) &
        (df_match['event'].isin(show_events))
    ].dropna(subset=['px', 'py'])

    fig = go.Figure(
        data=[go.Scatter(x=[], y=[], mode='markers',
                         name=EVENT_LABELS.get(e, e)) for e in show_events],
        frames=frames,
        layout=go.Layout(
            title_text="T = 0s",
            updatemenus=[dict(
                type="buttons", showactive=False,
                y=1.08, x=0.5, xanchor="center",
                buttons=[
                    dict(label="▶  Play",
                         method="animate",
                         args=[None, {"frame": {"duration": 400, "redraw": True},
                                      "fromcurrent": True}]),
                    dict(label="⏸  Pause",
                         method="animate",
                         args=[[None], {"frame": {"duration": 0, "redraw": False},
                                        "mode": "immediate"}]),
                ]
            )],
            sliders=[dict(
                steps=[dict(method="animate",
                            args=[[str(t)], {"mode": "immediate",
                                             "frame": {"duration": 300, "redraw": True}}],
                            label=f"{t}s") for t in time_steps],
                transition=dict(duration=0),
                x=0, y=0, len=1.0,
                currentvalue=dict(prefix="Time: ", suffix="s", visible=True, xanchor="center"),
            )]
        )
    )

    fig.add_layout_image(
        dict(source=f"data:image/png;base64,{b64}",
             xref="x", yref="y",
             x=0, y=0, sizex=W, sizey=H,
             sizing="stretch", opacity=1.0, layer="below")
    )

    _set_axes(fig, W, H)
    return fig


def _set_axes(fig, W, H):
    fig.update_xaxes(range=[0, W], showgrid=False, zeroline=False, showticklabels=False)
    fig.update_yaxes(range=[H, 0], showgrid=False, zeroline=False,
                     showticklabels=False, scaleanchor="x", scaleratio=1)
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=40, b=0),
        legend=dict(
            bgcolor="rgba(15,15,15,0.75)",
            font=dict(color="white", size=11),
            borderwidth=0,
            x=0.01, y=0.99,
            xanchor="left", yanchor="top",
        ),
        height=650,
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────
def sidebar(df: pd.DataFrame):
    st.sidebar.image(
        "https://img.shields.io/badge/LILA%20BLACK-Level%20Designer%20Tool-8B5CF6?style=for-the-badge",
        use_container_width=True,
    )
    st.sidebar.markdown("---")

    # Map selector
    available_maps = sorted(df['map_id'].dropna().unique().tolist()) if not df.empty else list(MAP_CONFIG.keys())
    map_id = st.sidebar.selectbox("🗺️  Map", available_maps)

    # Date filter
    dates = sorted(df['date'].dropna().unique().tolist()) if not df.empty else []
    selected_dates = st.sidebar.multiselect("📅  Date", dates, default=dates)

    # Match filter
    df_map = df[(df['map_id'] == map_id) & (df['date'].isin(selected_dates))] if not df.empty else df
    matches = sorted(df_map['match_id_clean'].dropna().unique().tolist())
    match_display = {m: m[:12] + "…" for m in matches}
    selected_matches = st.sidebar.multiselect(
        "🎮  Match", matches,
        format_func=lambda m: match_display.get(m, m),
        default=matches[:5] if matches else [],
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("**🎯 Event types**")

    col1, col2 = st.sidebar.columns(2)
    show_kills    = col1.checkbox("Kills",       value=True)
    show_deaths   = col2.checkbox("Deaths",      value=True)
    show_storm    = col1.checkbox("Storm",       value=True)
    show_loot     = col2.checkbox("Loot",        value=True)
    show_positions= col1.checkbox("Positions",   value=False)
    show_bots     = col2.checkbox("Bot events",  value=False)

    show_events = []
    if show_kills:     show_events += ["Kill"]
    if show_deaths:    show_events += ["Killed"]
    if show_storm:     show_events += ["KilledByStorm"]
    if show_loot:      show_events += ["Loot"]
    if show_positions: show_events += ["Position"]
    if show_bots:      show_events += ["BotKill", "BotKilled", "BotPosition"]

    st.sidebar.markdown("---")
    st.sidebar.markdown("**🔥 Heatmap overlay**")
    overlay_mode = st.sidebar.radio(
        "Overlay", ["None", "Traffic (all positions)", "Kill zones", "Death zones", "Loot zones"],
        label_visibility="collapsed"
    )

    heatmap_bins = st.sidebar.slider("Heatmap resolution", 30, 120, 60, 10)

    return map_id, selected_dates, selected_matches, show_events, overlay_mode, heatmap_bins


# ── Stats panel ───────────────────────────────────────────────────────────────
def show_stats(df: pd.DataFrame):
    if df.empty:
        return
    combat = df[df['event'].isin(COMBAT_EVENTS)]
    total_kills  = len(df[df['event'] == "Kill"])
    total_deaths = len(df[df['event'].isin({"Killed", "BotKilled", "KilledByStorm"})])
    storm_deaths = len(df[df['event'] == "KilledByStorm"])
    total_loot   = len(df[df['event'] == "Loot"])
    n_humans     = df[df['is_human']]['user_id'].nunique()
    n_matches    = df['match_id_clean'].nunique()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Matches",      n_matches)
    c2.metric("Human players", n_humans)
    c3.metric("Player kills", total_kills)
    c4.metric("Deaths",       total_deaths)
    c5.metric("Storm deaths", storm_deaths)
    c6.metric("Loot pickups", total_loot)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Resolve paths
    script_dir   = Path(__file__).parent
    data_dir     = str(script_dir / "data")
    minimap_dir  = str(script_dir / "minimaps")

    # Load data
    with st.spinner("Loading match data…"):
        df = load_data(data_dir)

    if df.empty:
        st.warning(
            "⚠️  No data found. Please place your parquet files in `data/February_XX/` subfolders "
            "and minimap images in `minimaps/`."
        )
        st.info("**Expected structure:**\n```\ndata/\n  February_10/\n    <user_id>_<match_id>.nakama-0\n  ...\nminimaps/\n  AmbroseValley_Minimap.png\n  GrandRift_Minimap.png\n  Lockdown_Minimap.jpg\n```")
        return

    # Sidebar filters
    map_id, selected_dates, selected_matches, show_events, overlay_mode, heatmap_bins = sidebar(df)

    # Filter data
    df_filtered = df[
        (df['map_id'] == map_id) &
        (df['date'].isin(selected_dates)) &
        (df['match_id_clean'].isin(selected_matches))
    ] if selected_matches else df[(df['map_id'] == map_id) & (df['date'].isin(selected_dates))]

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_map, tab_timeline, tab_players = st.tabs([
        "🗺️  Map View", "⏱️  Match Playback", "📊  Player Stats"
    ])

    # ── Tab 1: Map view ────────────────────────────────────────────────────────
    with tab_map:
        st.markdown(f"### {map_id}  —  Event Map")
        show_stats(df_filtered)
        st.markdown("")

        if df_filtered.empty:
            st.info("No data for current filters.")
        else:
            fig = build_figure(df_filtered, map_id, minimap_dir,
                               show_events, overlay_mode, heatmap_bins)
            st.plotly_chart(fig, use_container_width=True)

        # Legend
        with st.expander("Event legend"):
            cols = st.columns(4)
            for i, (ev, label) in enumerate(EVENT_LABELS.items()):
                color = EVENT_COLORS[ev]
                cols[i % 4].markdown(
                    f"<span style='color:{color};font-size:18px'>●</span> {label}",
                    unsafe_allow_html=True,
                )

    # ── Tab 2: Timeline playback ───────────────────────────────────────────────
    with tab_timeline:
        st.markdown("### Match Playback")
        st.caption("Select a single match to watch it unfold over time.")

        match_options = sorted(df_filtered['match_id_clean'].dropna().unique().tolist())
        if not match_options:
            st.info("No matches available for current filters.")
        else:
            sel_match = st.selectbox("Select match", match_options,
                                     format_func=lambda m: m[:20] + "…")
            df_match = df_filtered[df_filtered['match_id_clean'] == sel_match]

            if df_match.empty or 'ts_rel' not in df_match.columns:
                st.info("No timeline data for this match.")
            else:
                max_time = float(df_match['ts_rel'].max())
                n_events = len(df_match[df_match['event'].isin(COMBAT_EVENTS)])
                n_players = df_match[df_match['is_human']]['user_id'].nunique()

                c1, c2, c3 = st.columns(3)
                c1.metric("Match duration", f"{max_time:.0f}s")
                c2.metric("Human players", n_players)
                c3.metric("Combat events", n_events)

                if show_events:
                    with st.spinner("Building playback…"):
                        fig_tl = build_timeline_figure(
                            df_match, map_id, minimap_dir, show_events, max_time
                        )
                    st.plotly_chart(fig_tl, use_container_width=True)
                else:
                    st.info("Enable at least one event type in the sidebar.")

    # ── Tab 3: Player stats ────────────────────────────────────────────────────
    with tab_players:
        st.markdown("### Player Breakdown")

        if df_filtered.empty:
            st.info("No data for current filters.")
        else:
            # Kill/death per player
            kills  = df_filtered[df_filtered['event'] == "Kill"].groupby('user_id').size().rename("kills")
            deaths = df_filtered[df_filtered['event'].isin({"Killed","BotKilled","KilledByStorm"})]\
                        .groupby('user_id').size().rename("deaths")
            loot   = df_filtered[df_filtered['event'] == "Loot"].groupby('user_id').size().rename("loot")
            is_h   = df_filtered.drop_duplicates('user_id').set_index('user_id')['is_human']

            summary = pd.concat([kills, deaths, loot, is_h], axis=1).fillna(0)
            summary['kills']  = summary['kills'].astype(int)
            summary['deaths'] = summary['deaths'].astype(int)
            summary['loot']   = summary['loot'].astype(int)
            summary['type']   = summary['is_human'].map({True: "Human", False: "Bot"})
            summary['kd']     = (summary['kills'] / summary['deaths'].replace(0, 1)).round(2)
            summary = summary.reset_index().rename(columns={'user_id': 'Player ID'})
            summary['Player ID'] = summary['Player ID'].apply(lambda x: str(x)[:16]+"…" if len(str(x))>16 else str(x))

            # Filter: humans only toggle
            humans_only = st.checkbox("Show human players only", value=True)
            display_df = summary[summary['type'] == "Human"] if humans_only else summary
            display_df = display_df.sort_values('kills', ascending=False)

            st.dataframe(
                display_df[['Player ID', 'type', 'kills', 'deaths', 'kd', 'loot']]\
                    .rename(columns={'type':'Type','kd':'K/D','loot':'Loot'}),
                use_container_width=True, hide_index=True
            )

            # Kill distribution chart
            st.markdown("#### Kill distribution")
            fig_bar = px.bar(
                display_df.head(20).sort_values('kills'),
                x='kills', y='Player ID', orientation='h',
                color='kills', color_continuous_scale='Reds',
                labels={'kills': 'Kills'},
            )
            fig_bar.update_layout(
                showlegend=False, height=400,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#ccc"),
                yaxis=dict(tickfont=dict(size=10)),
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            # Event breakdown pie
            st.markdown("#### Event breakdown")
            event_counts = df_filtered[df_filtered['event'].isin(COMBAT_EVENTS | {"Loot"})]\
                .groupby('event').size().reset_index(name='count')
            event_counts['label'] = event_counts['event'].map(EVENT_LABELS)
            fig_pie = px.pie(event_counts, values='count', names='label',
                             color_discrete_sequence=px.colors.qualitative.Bold)
            fig_pie.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#ccc"), height=350,
            )
            st.plotly_chart(fig_pie, use_container_width=True)


if __name__ == "__main__":
    main()
