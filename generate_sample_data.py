"""
generate_sample_data.py
Run this once to create realistic sample parquet data for all 3 maps across 5 days.
Usage: python generate_sample_data.py
"""
import os
import uuid
import random
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime

random.seed(42)
np.random.seed(42)

MAP_CONFIG = {
    "AmbroseValley": {"scale": 900,  "origin_x": -370, "origin_z": -473,
                      "bounds": [(-370, 530), (-473, 427)]},
    "GrandRift":     {"scale": 581,  "origin_x": -290, "origin_z": -290,
                      "bounds": [(-290, 291), (-290, 291)]},
    "Lockdown":      {"scale": 1000, "origin_x": -500, "origin_z": -500,
                      "bounds": [(-500, 500), (-500, 500)]},
}

DAYS = [
    ("February_10", 120),
    ("February_11", 80),
    ("February_12", 72),
    ("February_13", 45),
    ("February_14", 22),  # partial
]

BASE_TS_MS = 1739145600000  # Feb 10 2026 00:00 UTC in ms

def rand_world(map_id, n=1):
    cfg = MAP_CONFIG[map_id]
    (xmin, xmax), (zmin, zmax) = cfg["bounds"]
    x = np.random.uniform(xmin, xmax, n)
    z = np.random.uniform(zmin, zmax, n)
    y = np.random.uniform(50, 250, n)
    return x, y, z

def simulate_path(start_x, start_z, n_steps, map_id):
    cfg = MAP_CONFIG[map_id]
    (xmin, xmax), (zmin, zmax) = cfg["bounds"]
    xs, zs = [start_x], [start_z]
    dx, dz = random.uniform(-5,5), random.uniform(-5,5)
    for _ in range(n_steps - 1):
        dx = dx * 0.9 + random.uniform(-4, 4)
        dz = dz * 0.9 + random.uniform(-4, 4)
        xs.append(np.clip(xs[-1] + dx, xmin, xmax))
        zs.append(np.clip(zs[-1] + dz, zmin, zmax))
    return np.array(xs), np.array(zs)

def make_match(match_id, map_id, n_humans=6, n_bots=20, day_offset_ms=0):
    rows = []
    match_duration_ms = random.randint(180_000, 420_000)
    map_cfg = MAP_CONFIG[map_id]
    (xmin, xmax), (zmin, zmax) = map_cfg["bounds"]

    human_ids  = [str(uuid.uuid4()) for _ in range(n_humans)]
    bot_ids    = [str(random.randint(100, 9999)) for _ in range(n_bots)]
    alive_h    = set(human_ids)
    alive_b    = set(bot_ids)

    # Position sampling (every ~2s for 5 min match)
    n_pos_steps = match_duration_ms // 2000
    ts_positions = np.linspace(0, match_duration_ms, n_pos_steps, dtype=int)

    for uid in human_ids:
        sx, sz = random.uniform(xmin, xmax), random.uniform(zmin, zmax)
        xs, zs = simulate_path(sx, sz, len(ts_positions), map_id)
        ys = np.random.uniform(50, 200, len(ts_positions))
        for i, ts in enumerate(ts_positions):
            rows.append({
                "user_id": uid, "match_id": match_id + ".nakama-0",
                "map_id": map_id,
                "x": float(xs[i]), "y": float(ys[i]), "z": float(zs[i]),
                "ts": BASE_TS_MS + day_offset_ms + int(ts),
                "event": b"Position",
            })

    for bid in bot_ids:
        sx, sz = random.uniform(xmin, xmax), random.uniform(zmin, zmax)
        xs, zs = simulate_path(sx, sz, len(ts_positions), map_id)
        ys = np.random.uniform(50, 200, len(ts_positions))
        for i, ts in enumerate(ts_positions):
            rows.append({
                "user_id": bid, "match_id": match_id + ".nakama-0",
                "map_id": map_id,
                "x": float(xs[i]), "y": float(ys[i]), "z": float(zs[i]),
                "ts": BASE_TS_MS + day_offset_ms + int(ts),
                "event": b"BotPosition",
            })

    # Combat events
    n_combat = random.randint(8, 25)
    for _ in range(n_combat):
        if len(alive_h) < 1:
            break
        ts = random.randint(30_000, match_duration_ms - 10_000)
        x, y, z = float(np.random.uniform(xmin, xmax)), 100.0, float(np.random.uniform(zmin, zmax))
        killer = random.choice(list(alive_h))
        # PvP kill
        if len(alive_h) > 1 and random.random() < 0.5:
            victims = [h for h in alive_h if h != killer]
            if victims:
                victim = random.choice(victims)
                alive_h.discard(victim)
                rows.append({"user_id": killer, "match_id": match_id+".nakama-0", "map_id": map_id,
                              "x": x, "y": y, "z": z, "ts": BASE_TS_MS+day_offset_ms+ts, "event": b"Kill"})
                rows.append({"user_id": victim, "match_id": match_id+".nakama-0", "map_id": map_id,
                              "x": x+random.uniform(-5,5), "y": y, "z": z+random.uniform(-5,5),
                              "ts": BASE_TS_MS+day_offset_ms+ts+50, "event": b"Killed"})
        # Bot kill
        elif alive_b:
            bot = random.choice(list(alive_b))
            alive_b.discard(bot)
            rows.append({"user_id": killer, "match_id": match_id+".nakama-0", "map_id": map_id,
                          "x": x, "y": y, "z": z, "ts": BASE_TS_MS+day_offset_ms+ts, "event": b"BotKill"})

    # Bot kills player
    for _ in range(random.randint(2, 8)):
        if not alive_h or not alive_b:
            break
        victim = random.choice(list(alive_h))
        alive_h.discard(victim)
        ts = random.randint(60_000, match_duration_ms - 5000)
        x, y, z = float(np.random.uniform(xmin,xmax)), 100.0, float(np.random.uniform(zmin,zmax))
        rows.append({"user_id": victim, "match_id": match_id+".nakama-0", "map_id": map_id,
                      "x": x, "y": y, "z": z, "ts": BASE_TS_MS+day_offset_ms+ts, "event": b"BotKilled"})

    # Storm deaths (push toward edge)
    storm_edge_x = xmax - map_cfg["scale"] * 0.15
    for uid in list(alive_h)[:random.randint(0,3)]:
        ts = random.randint(match_duration_ms//2, match_duration_ms - 5000)
        x = float(np.random.uniform(storm_edge_x, xmax))
        z = float(np.random.uniform(zmin, zmax))
        rows.append({"user_id": uid, "match_id": match_id+".nakama-0", "map_id": map_id,
                      "x": x, "y": 100.0, "z": z, "ts": BASE_TS_MS+day_offset_ms+ts,
                      "event": b"KilledByStorm"})

    # Loot events (clustered in specific zones)
    loot_centers = [(random.uniform(xmin+50, xmax-50), random.uniform(zmin+50, zmax-50))
                    for _ in range(3)]
    for uid in human_ids:
        n_loot = random.randint(1, 8)
        center = random.choice(loot_centers)
        for _ in range(n_loot):
            ts = random.randint(5000, match_duration_ms // 3)
            x = float(np.clip(center[0] + np.random.normal(0, 30), xmin, xmax))
            z = float(np.clip(center[1] + np.random.normal(0, 30), zmin, zmax))
            rows.append({"user_id": uid, "match_id": match_id+".nakama-0", "map_id": map_id,
                          "x": x, "y": 100.0, "z": z, "ts": BASE_TS_MS+day_offset_ms+ts,
                          "event": b"Loot"})

    return rows


def main():
    base_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(base_dir, exist_ok=True)

    maps = list(MAP_CONFIG.keys())
    day_offset = 0

    for day_name, n_matches in DAYS:
        day_dir = os.path.join(base_dir, day_name)
        os.makedirs(day_dir, exist_ok=True)

        for i in range(n_matches):
            match_id  = str(uuid.uuid4())
            map_id    = random.choice(maps)
            n_humans  = random.randint(4, 10)
            n_bots    = random.randint(10, 30)

            rows = make_match(match_id, map_id, n_humans, n_bots, day_offset)
            if not rows:
                continue

            df = pd.DataFrame(rows)
            # Convert ts to timestamp (ms)
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')

            schema = pa.schema([
                pa.field('user_id',  pa.string()),
                pa.field('match_id', pa.string()),
                pa.field('map_id',   pa.string()),
                pa.field('x',        pa.float32()),
                pa.field('y',        pa.float32()),
                pa.field('z',        pa.float32()),
                pa.field('ts',       pa.timestamp('ms')),
                pa.field('event',    pa.binary()),
            ])
            table = pa.Table.from_pandas(df, schema=schema)

            # Write unique files per human player in match
            human_ids = df[df['user_id'].str.contains('-', na=False)]['user_id'].unique()
            for uid in human_ids:
                player_df = df[df['user_id'].isin(
                    list(human_ids) +
                    df[~df['user_id'].str.contains('-', na=False)]['user_id'].unique().tolist()
                )]
                fname = f"{uid}_{match_id}.nakama-0"
                fpath = os.path.join(day_dir, fname)
                player_table = pa.Table.from_pandas(player_df, schema=schema)
                pq.write_table(player_table, fpath)
                break  # one file per match for demo (full data has one per player)

        day_offset += 86_400_000  # +1 day in ms
        print(f"✓  {day_name}: {n_matches} matches written")

    print("\nSample data generated in data/")


if __name__ == "__main__":
    main()
