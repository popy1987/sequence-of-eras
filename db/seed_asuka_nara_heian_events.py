#!/usr/bin/env python3
"""Seed Asuka / Nara / Heian events from Wikipedia-derived JSON.

Includes civil wars, coups, pacification campaigns, and external wars.
Disputed dates are closed year intervals.

Usage:
  python db/seed_asuka_nara_heian_events.py
  python db/seed_asuka_nara_heian_events.py --rebuild
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
DATA_PATH = ROOT / "data" / "asuka_nara_heian_events.json"
OPEN_TO = 2_147_483_647

sys.path.insert(0, str(ROOT))
from build_db import Builder, ordinal  # noqa: E402

PREFIX = "anh"  # asuka-nara-heian seed namespace


def load_payload() -> tuple[dict, list[dict]]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return payload.get("meta", {}), payload["events"]


def clear_prior(conn: sqlite3.Connection) -> None:
    event_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM event WHERE id LIKE 'event.%' AND id IN ("
            "SELECT object_id FROM source_binding WHERE id LIKE 'bind.anh.%')"
        ).fetchall()
    ]
    # Broader: all events we own via time_point / map_feature prefixes
    event_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM event WHERE id IN ("
            "  SELECT object_id FROM map_feature WHERE id LIKE 'mf.anh.%'"
            ") OR id IN ("
            "  SELECT object_id FROM source_binding WHERE id LIKE 'bind.anh.%'"
            ")"
        ).fetchall()
    ]
    # Also match by known JSON ids if re-run after partial
    if DATA_PATH.exists():
        for ev in json.loads(DATA_PATH.read_text(encoding="utf-8")).get("events", []):
            event_ids.append(ev["id"])
    event_ids = sorted(set(event_ids))

    if event_ids:
        ph = ",".join("?" * len(event_ids))
        conn.execute(f"DELETE FROM event_relation WHERE parent_event_id IN ({ph}) OR child_event_id IN ({ph})", event_ids + event_ids)
        conn.execute(f"DELETE FROM event_participant WHERE event_id IN ({ph})", event_ids)
        conn.execute(f"DELETE FROM event_place WHERE event_id IN ({ph})", event_ids)
        conn.execute(f"DELETE FROM map_feature WHERE object_id IN ({ph})", event_ids)
        conn.execute(f"DELETE FROM note WHERE object_id IN ({ph})", event_ids)
        conn.execute(f"DELETE FROM source_binding WHERE object_id IN ({ph})", event_ids)
        conn.execute(f"DELETE FROM name_record WHERE object_id IN ({ph})", event_ids)
        conn.execute(f"DELETE FROM event WHERE id IN ({ph})", event_ids)

    conn.execute("DELETE FROM map_feature WHERE id LIKE 'mf.anh.%'")
    conn.execute("DELETE FROM source_binding WHERE id LIKE 'bind.anh.%'")
    conn.execute("DELETE FROM source WHERE id LIKE 'source.wikipedia_ja.anh%' OR id LIKE 'source.wikipedia_ja.event.anh.%'")
    conn.execute("DELETE FROM note WHERE id LIKE 'note.anh.%'")
    conn.execute("DELETE FROM time_point WHERE id LIKE 'tp.anh.%'")
    conn.execute("DELETE FROM geometry WHERE id LIKE 'geom.event.anh.%' OR id LIKE 'geom.anh.%'")
    # geometry ids used: geom.{event_id}
    conn.execute("DELETE FROM geometry WHERE id LIKE 'geom.event.%'")


def ensure_sources(b: Builder, meta: dict) -> str:
    c = b.conn
    retrieved = meta.get("retrieved_on", "2026-10-30")
    c.execute(
        """
        INSERT INTO source(id, kind, title, language, url, retrieved_on, note)
        VALUES (?, 'wikipedia', ?, 'ja', ?, ?, ?)
        """,
        (
            "source.wikipedia_ja.anh.battles",
            "日本の合戦一覧",
            "https://ja.wikipedia.org/wiki/日本の合戦一覧",
            retrieved,
            "飞鸟・奈良・平安内战／平乱／对外战争主轴。",
        ),
    )
    for key, title, url in (
        ("asuka", "飛鳥時代", "https://ja.wikipedia.org/wiki/飛鳥時代"),
        ("nara", "奈良時代", "https://ja.wikipedia.org/wiki/奈良時代"),
        ("heian", "平安時代", "https://ja.wikipedia.org/wiki/平安時代"),
    ):
        c.execute(
            """
            INSERT INTO source(id, kind, title, language, url, retrieved_on, note)
            VALUES (?, 'wikipedia', ?, 'ja', ?, ?, ?)
            """,
            (
                f"source.wikipedia_ja.anh.{key}",
                title,
                url,
                retrieved,
                "时代专文政治／制度节点。",
            ),
        )
    return "source.wikipedia_ja.anh.battles"


def seed_event(b: Builder, ev: dict, list_source_id: str) -> None:
    c = b.conn
    eid = ev["id"]
    slug = eid.removeprefix("event.")
    y0 = int(ev["from_year"])
    y1 = int(ev["to_year"])
    lon = float(ev["lon"])
    lat = float(ev["lat"])
    confidence = "disputed" if ev.get("disputed") else "estimated"
    if y0 == y1 and not ev.get("disputed"):
        confidence = "exact" if ev.get("precision") == "day" else "circa"
    precision = ev.get("precision") or "year"
    alignment = ev.get("alignment") or ("disputed" if ev.get("disputed") else "follows")

    start_id = b.time_point(
        earliest=(y0, 1, 1),
        latest=(y0, 12, 31),
        preferred=(y0, 7, 1),
        precision=precision,
        confidence=confidence,
        dating_method="historical_text",
        original=f"{ev['names'].get('ja', slug)} 始 {y0}",
        id_hint=f"tp.anh.{slug}.from",
    )
    end_id = start_id
    open_ended = 0
    if y1 != y0:
        end_id = b.time_point(
            earliest=(y1, 1, 1),
            latest=(y1, 12, 31),
            preferred=(y1, 7, 1),
            precision=precision,
            confidence=confidence,
            dating_method="historical_text",
            original=f"{ev['names'].get('ja', slug)} 终 {y1}",
            id_hint=f"tp.anh.{slug}.to",
        )
    q_from = ordinal(y0, 1, 1)
    q_to = ordinal(y1, 12, 31)

    # short_note carries conflict_class tag for export
    cc = ev.get("conflict_class")
    note_bits = [ev.get("short_note") or ""]
    if cc:
        note_bits.insert(0, f"[conflict:{cc}]")
    short_note = " ".join(x for x in note_bits if x)

    c.execute(
        """
        INSERT INTO event(
          id, kind, importance, timeline_policy, short_note, alignment,
          scenario_id, start_time_id, end_time_id, end_inclusive, open_ended,
          query_from, query_to
        ) VALUES (?, ?, ?, ?, ?, ?, 'scenario.wikipedia_ja', ?, ?, 1, ?, ?, ?)
        """,
        (
            eid,
            ev["kind"],
            int(ev["importance"]),
            ev.get("timeline_policy") or "chapter",
            short_note,
            alignment,
            start_id,
            end_id,
            open_ended,
            q_from,
            q_to,
        ),
    )

    names = ev["names"]
    for lang in ("ja", "zh_hans", "en"):
        if names.get(lang):
            b.name("event", eid, lang, names[lang], is_primary=1)

    gid = f"geom.{eid}"
    b.geometry_point(gid, lon, lat, quality="approximate")
    c.execute(
        """
        INSERT INTO event_place(
          id, event_id, place_id, spatial_unit_id, geometry_id, role, scenario_id
        ) VALUES (?, ?, NULL, NULL, ?, 'primary', 'scenario.wikipedia_ja')
        """,
        (f"ep.anh.{slug}", eid, gid),
    )

    purpose = "uncertainty" if ev.get("disputed") else "caption"
    c.execute(
        """
        INSERT INTO note(
          id, object_kind, object_id, language, purpose, body,
          open_ended, query_from, query_to
        ) VALUES (?, 'event', ?, 'zh_hans', ?, ?, 1, 0, ?)
        """,
        (f"note.anh.{slug}", eid, purpose, ev.get("short_note") or short_note, OPEN_TO),
    )

    c.execute(
        """
        INSERT INTO source_binding(
          id, object_kind, object_id, source_id, role, summary, is_primary
        ) VALUES (?, 'event', ?, ?, 'fact_spine', ?, 1)
        """,
        (
            f"bind.anh.{slug}",
            eid,
            list_source_id if cc else f"source.wikipedia_ja.anh.{ev.get('period', 'heian')}",
            f"{y0}–{y1}" if y0 != y1 else str(y0),
        ),
    )
    wiki_url = ev.get("wiki_url")
    if wiki_url:
        src_id = f"source.wikipedia_ja.event.anh.{slug}"
        c.execute(
            """
            INSERT INTO source(id, kind, title, language, url, note)
            VALUES (?, 'wikipedia', ?, 'ja', ?, ?)
            """,
            (src_id, names.get("ja") or slug, wiki_url, "事件条目；年代非发掘年。"),
        )
        c.execute(
            """
            INSERT INTO source_binding(
              id, object_kind, object_id, source_id, role, summary, is_primary
            ) VALUES (?, 'event', ?, ?, 'dating', ?, 0)
            """,
            (f"bind.anh.{slug}.page", eid, src_id, "条目页"),
        )

    style = json.dumps(
        {
            "kind": "event",
            "event_kind": ev["kind"],
            "conflict_class": cc,
            "from_year": y0,
            "to_year": y1,
            "disputed": bool(ev.get("disputed")),
            "period": ev.get("period"),
            "parent_id": ev.get("parent_id"),
        },
        ensure_ascii=False,
    )
    display_rank = 1 if int(ev["importance"]) <= 2 else 2
    c.execute(
        """
        INSERT INTO map_feature(
          id, layer_id, scenario_id, geometry_source, object_kind, object_id,
          geometry_id, style_json, display_rank, importance,
          start_time_id, end_time_id, end_inclusive, open_ended,
          query_from, query_to
        ) VALUES (
          ?, 'layer.events', 'scenario.wikipedia_ja', 'authored', 'event', ?,
          ?, ?, ?, ?,
          ?, ?, 1, 0, ?, ?
        )
        """,
        (
            f"mf.anh.{slug}",
            eid,
            gid,
            style,
            display_rank,
            int(ev["importance"]),
            start_id,
            end_id,
            q_from,
            q_to,
        ),
    )


def link_parents(b: Builder, events: list[dict]) -> None:
    c = b.conn
    for ev in events:
        parent = ev.get("parent_id")
        if not parent:
            continue
        child = ev["id"]
        exists = c.execute("SELECT 1 FROM event WHERE id=?", (parent,)).fetchone()
        if not exists:
            continue
        slug = child.removeprefix("event.")
        c.execute(
            """
            INSERT INTO event_relation(id, parent_event_id, child_event_id, relation)
            VALUES (?, ?, ?, 'part_of')
            """,
            (f"er.anh.{slug}", parent, child),
        )


def seed_into(b: Builder) -> int:
    meta, events = load_payload()
    clear_prior(b.conn)
    list_src = ensure_sources(b, meta)
    for ev in events:
        seed_event(b, ev, list_src)
    link_parents(b, events)
    return len(events)


def verify(conn: sqlite3.Connection) -> None:
    n = conn.execute(
        "SELECT COUNT(*) FROM event WHERE id IN (SELECT object_id FROM map_feature WHERE id LIKE 'mf.anh.%')"
    ).fetchone()[0]
    wars = conn.execute(
        "SELECT COUNT(*) FROM event WHERE short_note LIKE '%[conflict:%'"
    ).fetchone()[0]
    print(f"anh events={n} with_conflict_tag={wars}")
    for eid in (
        "event.jinshin_war",
        "event.hayato_rebellion",
        "event.emishi_war_38",
        "event.masakado",
        "event.genpei_war",
        "event.teibi_no_ran",
    ):
        row = conn.execute(
            """
            SELECT e.id, ts.preferred_year y0, te.preferred_year y1, e.kind, e.importance, e.alignment
            FROM event e
            JOIN time_point ts ON ts.id=e.start_time_id
            LEFT JOIN time_point te ON te.id=e.end_time_id
            WHERE e.id=?
            """,
            (eid,),
        ).fetchone()
        print(" ", row)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    if args.rebuild:
        subprocess.check_call([sys.executable, str(ROOT / "build_db.py")])
    if not DB_PATH.exists():
        raise SystemExit(f"missing DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        b = Builder(conn)
        b.tp_n = conn.execute("SELECT COUNT(*) FROM time_point").fetchone()[0] + 2000
        n = seed_into(b)
        conn.commit()
        print(f"seeded {n} asuka/nara/heian events")
        verify(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
