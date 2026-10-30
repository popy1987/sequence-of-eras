#!/usr/bin/env python3
"""Seed Kofun burial/construction dates from Wikipedia-derived JSON.

Dating policy: Wikipedia 「築造時期」 as burial/mound-construction horizon —
NOT excavation year. Disputed dates are stored as closed year intervals.

Usage:
  python db/seed_kofun_burials.py              # mutate existing DB
  python db/seed_kofun_burials.py --rebuild     # rebuild DB then seed
  from build_db: seed_into(builder)
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "sequence_of_eras.sqlite"
DATA_PATH = ROOT / "data" / "kofun_burials.json"
OPEN_TO = 2_147_483_647

# Import shared helpers from build_db without running main.
sys.path.insert(0, str(ROOT))
from build_db import Builder, ordinal  # noqa: E402


def load_tombs() -> tuple[dict, list[dict]]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return payload.get("meta", {}), payload["tombs"]


def clear_prior_kofun(conn: sqlite3.Connection) -> None:
    """Idempotent wipe of previous kofun seed rows."""
    place_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM place WHERE id LIKE 'place.kofun.%'"
        ).fetchall()
    ]
    if not place_ids:
        # also clear orphaned sources/bindings if re-run after partial failure
        pass
    else:
        placeholders = ",".join("?" * len(place_ids))
        geom_ids = [f"geom.{pid}" for pid in place_ids]
        # Children first, then place, then geometry/time_point.
        for table, col in (
            ("map_feature", "object_id"),
            ("place_function", "place_id"),
            ("note", "object_id"),
            ("source_binding", "object_id"),
            ("external_id", "object_id"),
            ("name_record", "object_id"),
        ):
            conn.execute(
                f"DELETE FROM {table} WHERE {col} IN ({placeholders})",
                place_ids,
            )
        conn.execute(
            f"DELETE FROM place WHERE id IN ({placeholders})",
            place_ids,
        )
        conn.execute(
            f"DELETE FROM geometry WHERE id IN ({placeholders})",
            geom_ids,
        )
        for pid in place_ids:
            slug = pid.removeprefix("place.kofun.")
            conn.execute(
                "DELETE FROM time_point WHERE id LIKE ?",
                (f"tp.kofun.{slug}.%",),
            )

    conn.execute("DELETE FROM source_binding WHERE id LIKE 'bind.kofun.%'")
    conn.execute("DELETE FROM source WHERE id LIKE 'source.wikipedia_ja.kofun%'")
    conn.execute("DELETE FROM note WHERE id LIKE 'note.kofun.%'")
    conn.execute("DELETE FROM map_feature WHERE id LIKE 'mf.kofun.%'")
    conn.execute("DELETE FROM time_point WHERE id LIKE 'tp.kofun.%'")
    conn.execute("DELETE FROM name_record WHERE object_id LIKE 'place.kofun.%'")
    conn.execute("DELETE FROM place WHERE id LIKE 'place.kofun.%'")
    conn.execute("DELETE FROM geometry WHERE id LIKE 'geom.place.kofun.%'")


def ensure_sources(b: Builder, meta: dict) -> str:
    c = b.conn
    list_url = meta.get(
        "primary_list",
        "https://ja.wikipedia.org/wiki/日本の大規模古墳一覧",
    )
    retrieved = meta.get("retrieved_on", "2026-10-30")
    c.execute(
        """
        INSERT INTO source(id, kind, title, language, url, retrieved_on, note)
        VALUES (?, 'wikipedia', ?, 'ja', ?, ?, ?)
        """,
        (
            "source.wikipedia_ja.kofun_large_list",
            "日本の大規模古墳一覧",
            list_url,
            retrieved,
            "墳丘長≥200m一覧；時期栏为築造编年，用作埋入／营建代理。",
        ),
    )
    c.execute(
        """
        INSERT INTO source(id, kind, title, language, url, retrieved_on, note)
        VALUES (?, 'wikipedia', ?, 'ja', ?, ?, ?)
        """,
        (
            "source.wikipedia_ja.kofun_period",
            "古墳時代",
            "https://ja.wikipedia.org/wiki/古墳時代",
            retrieved,
            "古坟时代编年背景。",
        ),
    )
    return "source.wikipedia_ja.kofun_large_list"


def seed_tomb(b: Builder, tomb: dict, list_source_id: str) -> None:
    c = b.conn
    pid = tomb["id"]
    slug = pid.removeprefix("place.kofun.")
    lon = float(tomb["lon"])
    lat = float(tomb["lat"])
    y0 = int(tomb["burial_from"])
    y1 = int(tomb["burial_to"])
    if y1 < y0:
        raise ValueError(f"{pid}: burial_to < burial_from")

    confidence = tomb.get("confidence") or (
        "disputed" if tomb.get("disputed") else "estimated"
    )
    precision = tomb.get("precision") or "decade"
    period_code = tomb.get("wiki_period_code") or f"{y0}-{y1}"

    gid = f"geom.{pid}"
    b.geometry_point(gid, lon, lat, quality="approximate")

    c.execute(
        """
        INSERT INTO place(id, kind, lon, lat, reliability_radius_m, geometry_id)
        VALUES (?, 'kofun', ?, ?, ?, ?)
        """,
        (
            pid,
            lon,
            lat,
            tomb.get("reliability_radius_m"),
            gid,
        ),
    )

    # Interval endpoints: start = burial_from year, end = burial_to year.
    # original_expression preserves Wikipedia century code.
    start_id = b.time_point(
        earliest=(y0, 1, 1),
        latest=(y0, 12, 31),
        preferred=(y0, 7, 1),
        precision=precision,
        confidence=confidence,
        dating_method="historical_text",
        original=f"築造／埋入始点 ≈ {period_code} → {y0}",
        id_hint=f"tp.kofun.{slug}.burial_from",
    )
    end_id = b.time_point(
        earliest=(y1, 1, 1),
        latest=(y1, 12, 31),
        preferred=(y1, 7, 1),
        precision=precision,
        confidence=confidence,
        dating_method="historical_text",
        original=f"築造／埋入终点 ≈ {period_code} → {y1}",
        id_hint=f"tp.kofun.{slug}.burial_to",
    )
    q_from = ordinal(y0, 1, 1)
    q_to = ordinal(y1, 12, 31)

    c.execute(
        """
        INSERT INTO place_function(
          id, place_id, function_kind, actor_id, scenario_id,
          start_time_id, end_time_id, end_inclusive, open_ended,
          query_from, query_to
        ) VALUES (?, ?, 'site_occupation', NULL, 'scenario.wikipedia_ja',
                  ?, ?, 1, 0, ?, ?)
        """,
        (f"pf.kofun.{slug}.occupation", pid, start_id, end_id, q_from, q_to),
    )

    names = tomb["names"]
    for lang, key in (("ja", "ja"), ("zh_hans", "zh_hans"), ("en", "en")):
        if key in names and names[key]:
            b.name("place", pid, lang, names[key], is_primary=1)

    aliases = tomb.get("aliases") or {}
    if "ja" in aliases:
        b.name("place", pid, "ja", aliases["ja"], kind="historical", is_primary=0)

    note_body = tomb.get("note_zh") or (
        f"维基築造时期「{period_code}」→ 埋入／营建区间 {y0}–{y1} CE。"
    )
    purpose = "uncertainty" if tomb.get("disputed") else "caption"
    c.execute(
        """
        INSERT INTO note(
          id, object_kind, object_id, language, purpose, body,
          open_ended, query_from, query_to
        ) VALUES (?, 'place', ?, 'zh_hans', ?, ?, 1, 0, ?)
        """,
        (f"note.kofun.{slug}", pid, purpose, note_body, OPEN_TO),
    )

    c.execute(
        """
        INSERT INTO source_binding(
          id, object_kind, object_id, source_id, role, summary, is_primary
        ) VALUES (?, 'place', ?, ?, 'dating', ?, 1)
        """,
        (
            f"bind.kofun.{slug}.list",
            pid,
            list_source_id,
            f"築造时期 {period_code} → {y0}–{y1}",
        ),
    )
    wiki_url = tomb.get("wiki_url")
    if wiki_url:
        src_id = f"source.wikipedia_ja.kofun.{slug}"
        c.execute(
            """
            INSERT INTO source(id, kind, title, language, url, note)
            VALUES (?, 'wikipedia', ?, 'ja', ?, ?)
            """,
            (
                src_id,
                names.get("ja") or slug,
                wiki_url,
                "单坟条目；年代取築造／埋入，非发掘年。",
            ),
        )
        c.execute(
            """
            INSERT INTO source_binding(
              id, object_kind, object_id, source_id, role, summary, is_primary
            ) VALUES (?, 'place', ?, ?, 'fact_spine', ?, 0)
            """,
            (
                f"bind.kofun.{slug}.page",
                pid,
                src_id,
                "条目页",
            ),
        )

    # Map feature on sites layer for the burial interval.
    style = json.dumps(
        {
            "kind": "kofun",
            "length_m": tomb.get("length_m"),
            "rank": tomb.get("rank"),
            "burial_from": y0,
            "burial_to": y1,
            "disputed": bool(tomb.get("disputed")),
        },
        ensure_ascii=False,
    )
    importance = 5
    length = tomb.get("length_m") or 0
    if length >= 300:
        importance = 5
    elif length >= 200:
        importance = 4
    elif length >= 150:
        importance = 3
    else:
        importance = 3

    c.execute(
        """
        INSERT INTO map_feature(
          id, layer_id, scenario_id, geometry_source, object_kind, object_id,
          geometry_id, style_json, display_rank, importance,
          start_time_id, end_time_id, end_inclusive, open_ended,
          query_from, query_to
        ) VALUES (
          ?, 'layer.sites', 'scenario.wikipedia_ja', 'authored', 'place', ?,
          ?, ?, 1, ?,
          ?, ?, 1, 0, ?, ?
        )
        """,
        (
            f"mf.kofun.{slug}",
            pid,
            gid,
            style,
            importance,
            start_id,
            end_id,
            q_from,
            q_to,
        ),
    )


def seed_into(b: Builder) -> int:
    meta, tombs = load_tombs()
    clear_prior_kofun(b.conn)
    list_src = ensure_sources(b, meta)
    for tomb in tombs:
        seed_tomb(b, tomb, list_src)
    return len(tombs)


def verify(conn: sqlite3.Connection) -> None:
    n_places = conn.execute(
        "SELECT COUNT(*) FROM place WHERE kind='kofun'"
    ).fetchone()[0]
    n_pf = conn.execute(
        "SELECT COUNT(*) FROM place_function WHERE id LIKE 'pf.kofun.%'"
    ).fetchone()[0]
    n_mf = conn.execute(
        "SELECT COUNT(*) FROM map_feature WHERE id LIKE 'mf.kofun.%'"
    ).fetchone()[0]
    print(f"kofun places={n_places} place_functions={n_pf} map_features={n_mf}")
    samples = [
        "place.kofun.hashihaka",
        "place.kofun.daisenryo",
        "place.kofun.imashirozuka",
        "place.kofun.ishibutai",
        "place.kofun.inariyama_gyoda",
    ]
    for pid in samples:
        row = conn.execute(
            """
            SELECT p.id, ts.preferred_year AS y0, te.preferred_year AS y1,
                   ts.confidence, ts.original_expression
            FROM place p
            JOIN place_function pf ON pf.place_id = p.id
            JOIN time_point ts ON ts.id = pf.start_time_id
            JOIN time_point te ON te.id = pf.end_time_id
            WHERE p.id = ?
            """,
            (pid,),
        ).fetchone()
        if not row:
            print(f"  MISSING {pid}")
        else:
            print(
                f"  {row[0]} burial {row[1]}–{row[2]} "
                f"({row[3]}) {row[4]}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Run build_db.py first, then seed kofun rows.",
    )
    args = parser.parse_args()

    if args.rebuild:
        subprocess.check_call([sys.executable, str(ROOT / "build_db.py")])

    if not DB_PATH.exists():
        raise SystemExit(f"missing DB: {DB_PATH}; run build_db.py or --rebuild")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        b = Builder(conn)
        # Align tp counter away from existing ids
        max_tp = conn.execute(
            "SELECT COUNT(*) FROM time_point"
        ).fetchone()[0]
        b.tp_n = max_tp + 1000
        n = seed_into(b)
        conn.commit()
        print(f"seeded {n} kofun tombs into {DB_PATH}")
        verify(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
