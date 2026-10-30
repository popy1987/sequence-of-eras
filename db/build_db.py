#!/usr/bin/env python3
"""Build the local single-file SQLite database from schema.sql + seed data.

Usage:
  python db/build_db.py
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA = ROOT / "schema.sql"
DB_PATH = ROOT / "sequence_of_eras.sqlite"
OPEN_TO = 2_147_483_647  # open-ended query_to sentinel


def to_jdn(year: int, month: int, day: int) -> int:
    """Proleptic Gregorian astronomical year -> Julian Day Number."""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


EPOCH_JDN = to_jdn(-200_000, 1, 1)


def ordinal(year: int, month: int = 1, day: int = 1) -> int:
    return to_jdn(year, month, day) - EPOCH_JDN


def year_span(start_year: int, end_year: int | None, open_ended: bool = False):
    """Whole-year span helpers: Jan 1 .. Dec 31, preferred Jul 1."""
    start = {
        "earliest": (start_year, 1, 1),
        "latest": (start_year, 12, 31),
        "preferred": (start_year, 7, 1),
        "precision": "year",
        "confidence": "exact",
        "dating_method": "calendar",
    }
    if open_ended or end_year is None:
        end = None
        q_to = OPEN_TO
    else:
        end = {
            "earliest": (end_year, 1, 1),
            "latest": (end_year, 12, 31),
            "preferred": (end_year, 7, 1),
            "precision": "year",
            "confidence": "exact",
            "dating_method": "calendar",
        }
        q_to = ordinal(end_year, 12, 31)
    q_from = ordinal(start_year, 1, 1)
    return start, end, q_from, q_to


class Builder:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.tp_n = 0

    def exec_script(self, sql: str) -> None:
        self.conn.executescript(sql)

    def time_point(
        self,
        *,
        earliest: tuple[int, int, int],
        latest: tuple[int, int, int],
        preferred: tuple[int, int, int],
        precision: str,
        confidence: str,
        dating_method: str = "calendar",
        original: str | None = None,
        bp_epoch_year: int | None = None,
        id_hint: str | None = None,
    ) -> str:
        self.tp_n += 1
        tp_id = id_hint or f"tp.{self.tp_n:05d}"
        oe, om, od = earliest
        le, lm, ld = latest
        pe, pm, pd = preferred
        self.conn.execute(
            """
            INSERT INTO time_point (
              id, earliest_year, earliest_month, earliest_day,
              latest_year, latest_month, latest_day,
              preferred_year, preferred_month, preferred_day,
              precision, confidence, dating_method, original_expression,
              bp_epoch_year, ordinal_earliest, ordinal_latest, ordinal_preferred
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tp_id,
                oe, om, od,
                le, lm, ld,
                pe, pm, pd,
                precision, confidence, dating_method, original,
                bp_epoch_year,
                ordinal(*earliest),
                ordinal(*latest),
                ordinal(*preferred),
            ),
        )
        return tp_id

    def span_from_years(
        self,
        start_year: int,
        end_year: int | None = None,
        *,
        open_ended: bool = False,
        precision: str = "year",
        confidence: str = "exact",
        id_prefix: str | None = None,
    ):
        start_spec, end_spec, q_from, q_to = year_span(start_year, end_year, open_ended)
        start_id = self.time_point(
            earliest=start_spec["earliest"],
            latest=start_spec["latest"],
            preferred=start_spec["preferred"],
            precision=precision,
            confidence=confidence,
            id_hint=f"{id_prefix}.start" if id_prefix else None,
        )
        end_id = None
        if end_spec is not None:
            end_id = self.time_point(
                earliest=end_spec["earliest"],
                latest=end_spec["latest"],
                preferred=end_spec["preferred"],
                precision=precision,
                confidence=confidence,
                id_hint=f"{id_prefix}.end" if id_prefix else None,
            )
        return start_id, end_id, q_from, q_to, 1 if open_ended else 0

    def day_point(self, year: int, month: int, day: int, *, id_hint: str | None = None) -> str:
        d = (year, month, day)
        return self.time_point(
            earliest=d,
            latest=d,
            preferred=d,
            precision="day",
            confidence="exact",
            id_hint=id_hint,
        )

    def name(
        self,
        object_kind: str,
        object_id: str,
        language: str,
        text: str,
        *,
        kind: str = "common",
        is_primary: int = 1,
        party_actor_id: str | None = None,
        open_ended: int = 1,
    ) -> str:
        nid = f"name.{object_kind}.{object_id}.{language}"
        if party_actor_id:
            nid = f"{nid}.{party_actor_id.split('.')[-1]}"
        # dedupe suffix if collision
        existing = self.conn.execute("SELECT 1 FROM name_record WHERE id=?", (nid,)).fetchone()
        if existing:
            nid = f"{nid}.{kind}"
        self.conn.execute(
            """
            INSERT INTO name_record (
              id, object_kind, object_id, language, text, kind,
              is_primary, party_actor_id, open_ended, query_from, query_to
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                nid,
                object_kind,
                object_id,
                language,
                text,
                kind,
                is_primary,
                party_actor_id,
                open_ended,
                OPEN_TO,
            ),
        )
        return nid

    def geometry_point(self, gid: str, lon: float, lat: float, *, quality: str = "approximate") -> str:
        geojson = json.dumps({"type": "Point", "coordinates": [lon, lat]}, ensure_ascii=False)
        self.conn.execute(
            """
            INSERT INTO geometry (
              id, shape_type, detail_level, bbox_west, bbox_south, bbox_east, bbox_north,
              label_lon, label_lat, boundary_quality, geojson, open_ended, query_from, query_to
            ) VALUES (?, 'point', 'overview', ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?)
            """,
            (gid, lon, lat, lon, lat, lon, lat, quality, geojson, OPEN_TO),
        )
        return gid


def seed(b: Builder) -> None:
    c = b.conn

    c.execute(
        "INSERT INTO schema_meta(key, value) VALUES (?, ?), (?, ?), (?, ?), (?, ?)",
        (
            "schema_version", "0.1.0",
            "logical_design", "doc/数据库设计.md",
            "engine", "sqlite3",
            "created_by", "db/build_db.py",
        ),
    )

    # Scenarios
    scenarios = [
        ("scenario.wikipedia_ja", "wikipedia_consensus", 1, "日文维基默认情景"),
        ("scenario.wikipedia_zh", "wikipedia_consensus", 0, "中文维基差异情景"),
        ("scenario.legendary", "legendary", 0, "传说叙事"),
        ("scenario.yamatai_kinai", "scholarly_alternative", 0, "邪马台国畿内说"),
        ("scenario.yamatai_kyushu", "scholarly_alternative", 0, "邪马台国九州说"),
        ("scenario.paleolithic_early", "scholarly_alternative", 0, "更早旧石器争议材料"),
    ]
    c.executemany(
        "INSERT INTO scenario(id, kind, is_default, note) VALUES (?, ?, ?, ?)",
        scenarios,
    )
    for sid, _, _, note in scenarios:
        b.name("scenario", sid, "zh_hans", note.split("。")[0] if note else sid, kind="short")

    # Sources (stubs)
    c.executemany(
        """
        INSERT INTO source(id, kind, title, language, url, note)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "source.wikipedia_ja.history_of_japan",
                "wikipedia",
                "日本の歴史",
                "ja",
                "https://ja.wikipedia.org/wiki/日本の歴史",
                "默认史实主轴",
            ),
            (
                "source.wikipedia_ja.era_names",
                "wikipedia",
                "元号一覧 (日本)",
                "ja",
                "https://ja.wikipedia.org/wiki/元号一覧_(日本)",
                "日本年号列表",
            ),
            (
                "source.design.doc",
                "book",
                "数据库设计.md",
                "zh",
                None,
                "项目逻辑设计",
            ),
        ],
    )

    # Map layers
    layers = [
        ("layer.paleogeography", 10, 1),
        ("layer.culture", 20, 1),
        ("layer.political", 30, 1),
        ("layer.contested", 40, 1),
        ("layer.dispute", 45, 1),
        ("layer.admin", 50, 0),
        ("layer.routes", 60, 0),
        ("layer.sites", 70, 1),
        ("layer.places", 80, 1),
        ("layer.events", 90, 1),
        ("layer.modern_reference", 100, 0),
        ("layer.legendary", 110, 0),
        ("layer.overseas", 120, 0),
    ]
    c.executemany(
        "INSERT INTO map_layer(id, sort_order, default_on) VALUES (?, ?, ?)",
        layers,
    )
    layer_names = {
        "layer.paleogeography": ("古地理", "Paleogeography"),
        "layer.culture": ("文化分布", "Culture"),
        "layer.political": ("政治范围", "Political"),
        "layer.contested": ("争夺与双重从属", "Contested"),
        "layer.dispute": ("争议地区", "Disputed regions"),
        "layer.admin": ("行政区划", "Administration"),
        "layer.routes": ("道路航路", "Routes"),
        "layer.sites": ("遗迹", "Sites"),
        "layer.places": ("地点", "Places"),
        "layer.events": ("事件", "Events"),
        "layer.modern_reference": ("现代对照", "Modern reference"),
        "layer.legendary": ("传说", "Legendary"),
        "layer.overseas": ("海外控制", "Overseas"),
    }
    for lid, (zh, en) in layer_names.items():
        b.name("map_layer", lid, "zh_hans", zh)
        b.name("map_layer", lid, "en", en)

    # Regions
    regions = [
        ("region.archipelago", None, "archipelago", -200000, None, True),
        ("region.core", "region.archipelago", "cultural_region", -14000, None, True),
        ("region.tohoku", "region.archipelago", "historical_frontier", -14000, None, True),
        ("region.kyushu_south", "region.archipelago", "cultural_region", -14000, None, True),
        ("region.hokkaido", "region.archipelago", "cultural_region", -14000, None, True),
        ("region.ryukyu", "region.archipelago", "island_chain", -5000, None, True),
        ("region.kinai", "region.core", "cultural_region", 200, None, True),
    ]
    for rid, parent, kind, y0, y1, open_ended in regions:
        s, e, qf, qt, oe = b.span_from_years(y0, y1, open_ended=open_ended, id_prefix=rid)
        c.execute(
            """
            INSERT INTO region(
              id, parent_id, kind, start_time_id, end_time_id,
              end_inclusive, open_ended, query_from, query_to
            ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (rid, parent, kind, s, e, oe, qf, qt),
        )
    region_names = {
        "region.archipelago": ("日本列岛", "Japanese archipelago"),
        "region.core": ("本州四国九州核心", "Core Honshu–Shikoku–Kyushu"),
        "region.tohoku": ("东北", "Tōhoku"),
        "region.kyushu_south": ("南九州", "Southern Kyushu"),
        "region.hokkaido": ("北海道", "Hokkaido"),
        "region.ryukyu": ("琉球", "Ryukyu"),
        "region.kinai": ("畿内", "Kinai"),
    }
    for rid, (zh, en) in region_names.items():
        b.name("region", rid, "zh_hans", zh)
        b.name("region", rid, "en", en)
        b.name("region", rid, "ja", {
            "region.archipelago": "日本列島",
            "region.core": "本州・四国・九州中核",
            "region.tohoku": "東北",
            "region.kyushu_south": "南九州",
            "region.hokkaido": "北海道",
            "region.ryukyu": "琉球",
            "region.kinai": "畿内",
        }[rid])

    # National periods (default scenario) — skeleton years from design §15.1
    periods = [
        ("period.paleolithic", None, "historiographic", None, -36050, -14000, False, 10, "旧石器时代", "旧石器時代", "Paleolithic"),
        ("period.jomon", None, "historiographic", None, -14000, -400, False, 20, "绳文时代", "縄文時代", "Jōmon"),
        ("period.yayoi", None, "historiographic", None, -400, 250, False, 30, "弥生时代", "弥生時代", "Yayoi"),
        ("period.kofun", None, "historiographic", None, 250, 592, False, 40, "古坟时代", "古墳時代", "Kofun"),
        ("period.asuka", None, "historiographic", None, 592, 710, False, 50, "飞鸟时代", "飛鳥時代", "Asuka"),
        ("period.nara", None, "historiographic", None, 710, 794, False, 60, "奈良时代", "奈良時代", "Nara"),
        ("period.heian", None, "historiographic", None, 794, 1185, False, 70, "平安时代", "平安時代", "Heian"),
        ("period.kamakura", None, "historiographic", None, 1185, 1333, False, 80, "镰仓时代", "鎌倉時代", "Kamakura"),
        ("period.kemmu", None, "historiographic", None, 1333, 1336, False, 90, "建武新政", "建武の新政", "Kenmu Restoration"),
        ("period.muromachi", None, "historiographic", None, 1336, 1573, False, 100, "室町时代", "室町時代", "Muromachi"),
        ("period.nanbokucho", "period.muromachi", "historiographic", None, 1336, 1392, False, 105, "南北朝时代", "南北朝時代", "Nanboku-chō"),
        ("period.sengoku", "period.muromachi", "historiographic", None, 1467, 1590, False, 110, "战国时代", "戦国時代", "Sengoku"),
        ("period.azuchi_momoyama", None, "historiographic", None, 1573, 1603, False, 120, "安土桃山时代", "安土桃山時代", "Azuchi–Momoyama"),
        ("period.edo", None, "historiographic", None, 1603, 1868, False, 130, "江户时代", "江戸時代", "Edo"),
        ("period.meiji", None, "regnal", None, 1868, 1912, False, 140, "明治时代", "明治時代", "Meiji"),
        ("period.taisho", None, "regnal", None, 1912, 1926, False, 150, "大正时代", "大正時代", "Taishō"),
        ("period.showa", None, "regnal", None, 1926, 1989, False, 160, "昭和时代", "昭和時代", "Shōwa"),
        ("period.heisei", None, "regnal", None, 1989, 2019, False, 170, "平成时代", "平成時代", "Heisei"),
        ("period.reiwa", None, "regnal", None, 2019, None, True, 180, "令和时代", "令和時代", "Reiwa"),
        # Regional
        ("period.ryukyu_gusuku", None, "regional", "region.ryukyu", 1100, 1429, False, 200, "古斯库时代", "グスク時代", "Gusuku period"),
        ("period.ryukyu_sanzan", None, "regional", "region.ryukyu", 1322, 1429, False, 210, "三山时代", "三山時代", "Sanzan period"),
        ("period.ryukyu_first_sho", None, "regional", "region.ryukyu", 1429, 1469, False, 220, "第一尚氏", "第一尚氏", "First Shō dynasty"),
        ("period.ryukyu_second_sho", None, "regional", "region.ryukyu", 1469, 1879, False, 230, "第二尚氏", "第二尚氏", "Second Shō dynasty"),
        ("period.okinawa_uscar", None, "regional", "region.ryukyu", 1945, 1972, False, 240, "冲绳美国统治", "沖縄のアメリカ統治", "US administration of Okinawa"),
    ]
    for pid, parent, kind, region_id, y0, y1, open_ended, sort, zh, ja, en in periods:
        s, e, qf, qt, oe = b.span_from_years(y0, y1, open_ended=open_ended, id_prefix=pid)
        # Reiwa / Heisei day precision overrides for modern era ends
        c.execute(
            """
            INSERT INTO period(
              id, parent_id, kind, region_id, scenario_id, sort_order,
              start_time_id, end_time_id, end_inclusive, open_ended, query_from, query_to
            ) VALUES (?, ?, ?, ?, 'scenario.wikipedia_ja', ?, ?, ?, 1, ?, ?, ?)
            """,
            (pid, parent, kind, region_id, sort, s, e, oe, qf, qt),
        )
        b.name("period", pid, "zh_hans", zh)
        b.name("period", pid, "ja", ja)
        b.name("period", pid, "en", en)

    # Patch Heisei/Reiwa to day precision endpoints from design
    # Heisei: 1989-01-08 .. 2019-04-30; Reiwa: 2019-05-01 open
    heisei_start = b.day_point(1989, 1, 8, id_hint="period.heisei.start_day")
    heisei_end = b.day_point(2019, 4, 30, id_hint="period.heisei.end_day")
    reiwa_start = b.day_point(2019, 5, 1, id_hint="period.reiwa.start_day")
    c.execute(
        """
        UPDATE period SET start_time_id=?, end_time_id=?, open_ended=0,
          query_from=?, query_to=?
        WHERE id='period.heisei'
        """,
        (heisei_start, heisei_end, ordinal(1989, 1, 8), ordinal(2019, 4, 30)),
    )
    c.execute(
        """
        UPDATE period SET start_time_id=?, end_time_id=NULL, open_ended=1,
          query_from=?, query_to=?
        WHERE id='period.reiwa'
        """,
        (reiwa_start, ordinal(2019, 5, 1), OPEN_TO),
    )

    # Actors needed for chronology + disputes
    actors = [
        ("actor.yamato_court", "polity", "historical", None, 250, None, True, "大和朝廷", "ヤマト王権", "Yamato court"),
        ("actor.japan", "modern_state", "historical", None, 1868, None, True, "日本国", "日本国", "Japan"),
        ("actor.prc", "modern_state", "historical", None, 1949, None, True, "中华人民共和国", "中華人民共和国", "People's Republic of China"),
        ("actor.roc", "modern_state", "historical", None, 1912, None, True, "中华民国", "中華民国", "Republic of China"),
        ("actor.rok", "modern_state", "historical", None, 1948, None, True, "大韩民国", "大韓民国", "Republic of Korea"),
        ("actor.russia", "modern_state", "historical", None, 1991, None, True, "俄罗斯联邦", "ロシア連邦", "Russian Federation"),
        ("actor.ryukyu_kingdom", "polity", "historical", None, 1429, 1879, False, "琉球王国", "琉球王国", "Ryukyu Kingdom"),
        ("actor.uscar", "occupation_authority", "historical", None, 1945, 1972, False, "琉球列岛美国民政府", "琉球列島米国民政府", "USCAR"),
        ("actor.satsuma_domain", "domain", "historical", None, 1602, 1871, False, "萨摩藩", "薩摩藩", "Satsuma Domain"),
        ("actor.tokugawa_shogunate", "polity", "historical", None, 1603, 1868, False, "江户幕府", "江戸幕府", "Tokugawa shogunate"),
    ]
    for aid, kind, hist, scen, y0, y1, open_ended, zh, ja, en in actors:
        s, e, qf, qt, oe = b.span_from_years(y0, y1, open_ended=open_ended, id_prefix=aid)
        c.execute(
            """
            INSERT INTO actor(
              id, kind, historicity, scenario_id, start_time_id, end_time_id,
              end_inclusive, open_ended, query_from, query_to
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (aid, kind, hist, scen, s, e, oe, qf, qt),
        )
        b.name("actor", aid, "zh_hans", zh)
        b.name("actor", aid, "ja", ja)
        b.name("actor", aid, "en", en)

    # Chronology tracks
    c.executemany(
        """
        INSERT INTO chronology_track(id, culture, role, actor_id, show_in_header, priority)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("chronology.japan_official", "japan", "primary", "actor.yamato_court", 1, 10),
            ("chronology.china_main", "china", "reference", None, 1, 20),
            ("chronology.japan_nanbokucho_south", "japan", "regional", "actor.yamato_court", 0, 30),
            ("chronology.china_regional", "china", "regional", None, 0, 40),
        ],
    )
    b.name("chronology_track", "chronology.japan_official", "zh_hans", "日本官方年号")
    b.name("chronology_track", "chronology.china_main", "zh_hans", "中国主体王朝纪年")
    b.name("chronology_track", "chronology.japan_official", "ja", "日本公式元号")
    b.name("chronology_track", "chronology.china_main", "ja", "中国主体王朝紀年")
    b.name("chronology_track", "chronology.japan_official", "en", "Japanese official eras")
    b.name("chronology_track", "chronology.china_main", "en", "Chinese main-dynasty chronology")

    # Seed sample Japanese eras (day/year precision). Full nengō list comes later.
    modern_eras = [
        ("era.keicho", "庆长", "Keichō", 1596, 10, 27, 1615, 7, 13),
        ("era.meiji", "明治", "Meiji", 1868, 10, 23, 1912, 7, 29),
        ("era.taisho", "大正", "Taishō", 1912, 7, 30, 1926, 12, 24),
        ("era.showa", "昭和", "Shōwa", 1926, 12, 25, 1989, 1, 7),
        ("era.heisei", "平成", "Heisei", 1989, 1, 8, 2019, 4, 30),
        ("era.reiwa", "令和", "Reiwa", 2019, 5, 1, None, None, None),
    ]
    # Minimal dynasty stubs for Japan modern + China PRC marker
    dyn_jp_s, dyn_jp_e, dyn_jp_qf, dyn_jp_qt, dyn_jp_oe = b.span_from_years(
        645, None, open_ended=True, id_prefix="dynasty.japan_imperial"
    )
    c.execute(
        """
        INSERT INTO dynasty(
          id, chronology_track_id, lineage, map_actor_id,
          start_time_id, end_time_id, end_inclusive, open_ended, query_from, query_to
        ) VALUES ('dynasty.japan_imperial', 'chronology.japan_official', 'main',
                  'actor.yamato_court', ?, ?, 1, ?, ?, ?)
        """,
        (dyn_jp_s, dyn_jp_e, dyn_jp_oe, dyn_jp_qf, dyn_jp_qt),
    )
    b.name("dynasty", "dynasty.japan_imperial", "zh_hans", "日本朝廷")
    b.name("dynasty", "dynasty.japan_imperial", "ja", "日本朝廷")
    b.name("dynasty", "dynasty.japan_imperial", "en", "Japanese imperial court")

    # Sample China main dynasties (skeleton)
    china_dynasties = [
        ("dynasty.zhou", "周", "Zhou", -841, -256),
        ("dynasty.qin", "秦", "Qin", -256, -207),
        ("dynasty.han_west", "汉", "Western Han", -206, 8),
        ("dynasty.tang", "唐", "Tang", 618, 907),
        ("dynasty.song", "大宋", "Song", 960, 1279),
        ("dynasty.yuan", "大元", "Yuan", 1279, 1368),
        ("dynasty.ming", "大明", "Ming", 1368, 1644),
        ("dynasty.qing", "大清", "Qing", 1644, 1911),
        ("dynasty.roc", "民国", "Republic of China", 1912, 1949),
        ("dynasty.prc", "中华人民共和国", "PRC", 1949, None),
    ]
    for did, zh, en, y0, y1 in china_dynasties:
        open_ended = y1 is None
        # PRC open from 1949-10-01
        if did == "dynasty.prc":
            s = b.day_point(1949, 10, 1, id_hint=f"{did}.start")
            e = None
            qf, qt, oe = ordinal(1949, 10, 1), OPEN_TO, 1
        elif did == "dynasty.roc":
            s = b.day_point(1912, 1, 1, id_hint=f"{did}.start")
            e = b.day_point(1949, 9, 30, id_hint=f"{did}.end")
            qf, qt, oe = ordinal(1912, 1, 1), ordinal(1949, 9, 30), 0
        else:
            s, e, qf, qt, oe = b.span_from_years(y0, y1, open_ended=open_ended, id_prefix=did)
        c.execute(
            """
            INSERT INTO dynasty(
              id, chronology_track_id, lineage,
              start_time_id, end_time_id, end_inclusive, open_ended, query_from, query_to
            ) VALUES (?, 'chronology.china_main', 'main', ?, ?, 1, ?, ?, ?)
            """,
            (did, s, e, oe, qf, qt),
        )
        b.name("dynasty", did, "zh_hans", zh)
        b.name("dynasty", did, "en", en)

    for eid, ja, en, y0, m0, d0, y1, m1, d1 in modern_eras:
        s = b.day_point(y0, m0, d0, id_hint=f"{eid}.start")
        if y1 is None:
            e, qf, qt, oe = None, ordinal(y0, m0, d0), OPEN_TO, 1
        else:
            e = b.day_point(y1, m1, d1, id_hint=f"{eid}.end")
            qf, qt, oe = ordinal(y0, m0, d0), ordinal(y1, m1, d1), 0
        cal = "gregorian" if y0 >= 1873 else "japanese_lunisolar"
        c.execute(
            """
            INSERT INTO era_name(
              id, chronology_track_id, dynasty_id, is_private, year_start_calendar,
              start_time_id, end_time_id, end_inclusive, open_ended, query_from, query_to
            ) VALUES (?, 'chronology.japan_official', 'dynasty.japan_imperial', 0, ?,
                      ?, ?, 1, ?, ?, ?)
            """,
            (eid, cal, s, e, oe, qf, qt),
        )
        b.name("era_name", eid, "ja", ja)
        b.name("era_name", eid, "zh_hans", ja)
        b.name("era_name", eid, "en", en)

    # Sample Chinese eras
    sample_cn_eras = [
        ("era.shaoxing", "dynasty.song", "绍兴", "Shaoxing", 1131, 1162),
        ("era.wanli", "dynasty.ming", "万历", "Wanli", 1573, 1620),
    ]
    for eid, did, zh, en, y0, y1 in sample_cn_eras:
        s, e, qf, qt, oe = b.span_from_years(y0, y1, id_prefix=eid)
        c.execute(
            """
            INSERT INTO era_name(
              id, chronology_track_id, dynasty_id, is_private, year_start_calendar,
              start_time_id, end_time_id, end_inclusive, open_ended, query_from, query_to
            ) VALUES (?, 'chronology.china_main', ?, 0, 'chinese_lunisolar',
                      ?, ?, 1, ?, ?, ?)
            """,
            (eid, did, s, e, oe, qf, qt),
        )
        b.name("era_name", eid, "zh_hans", zh)
        b.name("era_name", eid, "en", en)

    # Spatial frameworks (stubs)
    fw_s, fw_e, fw_qf, fw_qt, fw_oe = b.span_from_years(701, None, open_ended=True, id_prefix="framework.ryoseikoku")
    c.execute(
        """
        INSERT INTO spatial_framework(
          id, kind, boundary_quality, note, start_time_id, end_time_id,
          end_inclusive, open_ended, query_from, query_to
        ) VALUES ('framework.ryoseikoku', 'province', 'approximate',
                  '令制国骨架（几何待录入）', ?, ?, 1, ?, ?, ?)
        """,
        (fw_s, fw_e, fw_oe, fw_qf, fw_qt),
    )
    pref_s, pref_e, pref_qf, pref_qt, pref_oe = b.span_from_years(
        1871, None, open_ended=True, id_prefix="framework.prefecture_current"
    )
    c.execute(
        """
        INSERT INTO spatial_framework(
          id, kind, boundary_quality, note, start_time_id, end_time_id,
          end_inclusive, open_ended, query_from, query_to
        ) VALUES ('framework.prefecture_current', 'prefecture', 'modern_proxy',
                  '现代都道府县对照骨架（几何待录入）', ?, ?, 1, ?, ?, ?)
        """,
        (pref_s, pref_e, pref_oe, pref_qf, pref_qt),
    )
    c.execute(
        """
        INSERT INTO spatial_unit(
          id, framework_id, kind, start_time_id, end_time_id,
          end_inclusive, open_ended, query_from, query_to
        ) VALUES ('unit.prefecture.okinawa', 'framework.prefecture_current', 'prefecture',
                  ?, ?, 1, ?, ?, ?)
        """,
        (pref_s, pref_e, pref_oe, pref_qf, pref_qt),
    )
    b.name("spatial_unit", "unit.prefecture.okinawa", "zh_hans", "冲绳县")
    b.name("spatial_unit", "unit.prefecture.okinawa", "ja", "沖縄県")
    b.name("spatial_unit", "unit.prefecture.okinawa", "en", "Okinawa Prefecture")

    # Placeholder geometries for disputes (representative points; polygons later)
    b.geometry_point("geom.dispute.northern_territories", 147.8, 44.5, quality="schematic")
    b.geometry_point("geom.dispute.takeshima_dokdo", 131.87, 37.24, quality="schematic")
    b.geometry_point("geom.dispute.senkaku_diaoyu", 123.47, 25.74, quality="schematic")
    b.geometry_point("geom.dispute.ryukyu", 127.68, 26.21, quality="schematic")

    # Disputed regions
    disputes = [
        (
            "dispute.northern_territories",
            "island_group",
            "geom.dispute.northern_territories",
            None,
            1945,
            "北方四岛 / 南千岛争议区。库并列日俄说法，不作裁决。",
            "北方四岛／南千島",
            "Northern Territories / Southern Kurils",
        ),
        (
            "dispute.takeshima_dokdo",
            "island_group",
            "geom.dispute.takeshima_dokdo",
            None,
            1905,
            "竹岛 / 独岛争议区。库并列日韩说法，不作裁决。",
            "竹島／独島",
            "Takeshima / Dokdo",
        ),
        (
            "dispute.senkaku_diaoyu",
            "island_group",
            "geom.dispute.senkaku_diaoyu",
            None,
            1971,
            "尖阁 / 钓鱼岛争议区。库并列各方说法，不作裁决。",
            "尖閣／釣魚島",
            "Senkaku / Diaoyu",
        ),
        (
            "dispute.ryukyu",
            "archipelago_status",
            "geom.dispute.ryukyu",
            "unit.prefecture.okinawa",
            1609,
            "琉球列岛地位与历史归属对照区。含王国、处分、美治与返还后的多方叙事；库不作裁决。",
            "琉球",
            "Ryukyu",
        ),
    ]
    for did, kind, gid, uid, y0, note, ja, en in disputes:
        s, e, qf, qt, oe = b.span_from_years(y0, None, open_ended=True, id_prefix=did)
        c.execute(
            """
            INSERT INTO disputed_region(
              id, kind, spatial_unit_id, geometry_id, status, name_strategy,
              sensitivity, scenario_id, short_note,
              start_time_id, end_time_id, end_inclusive, open_ended, query_from, query_to
            ) VALUES (?, ?, ?, ?, 'active', 'all_party_names', 'high',
                      'scenario.wikipedia_ja', ?, ?, ?, 1, ?, ?, ?)
            """,
            (did, kind, uid, gid, note, s, e, oe, qf, qt),
        )
        b.name("disputed_region", did, "zh_hans", note.split("。")[0])
        b.name("disputed_region", did, "ja", ja)
        b.name("disputed_region", did, "en", en)

    # Dispute parties (current roles, open-ended)
    party_rows = [
        # Northern territories
        ("dispute.northern_territories", "actor.japan", "claims_sovereignty", "competing", "北方領土"),
        ("dispute.northern_territories", "actor.russia", "administers", "preferred", "Южные Курилы"),
        ("dispute.northern_territories", "actor.russia", "claims_sovereignty", "competing", "Южные Курилы"),
        # Takeshima / Dokdo
        ("dispute.takeshima_dokdo", "actor.japan", "claims_sovereignty", "competing", "竹島"),
        ("dispute.takeshima_dokdo", "actor.rok", "administers", "preferred", "독도"),
        ("dispute.takeshima_dokdo", "actor.rok", "claims_sovereignty", "competing", "독도"),
        # Senkaku / Diaoyu
        ("dispute.senkaku_diaoyu", "actor.japan", "administers", "preferred", "尖閣諸島"),
        ("dispute.senkaku_diaoyu", "actor.japan", "claims_sovereignty", "competing", "尖閣諸島"),
        ("dispute.senkaku_diaoyu", "actor.prc", "claims_sovereignty", "competing", "钓鱼岛及其附属岛屿"),
        ("dispute.senkaku_diaoyu", "actor.roc", "claims_sovereignty", "competing", "釣魚臺列嶼"),
        # Ryukyu
        ("dispute.ryukyu", "actor.japan", "administers", "preferred", "沖縄県"),
        ("dispute.ryukyu", "actor.japan", "claims_sovereignty", "preferred", "沖縄県"),
        ("dispute.ryukyu", "actor.ryukyu_kingdom", "claims_historical", "competing", "琉球国"),
    ]
    for i, (did, aid, role, claim, party_name) in enumerate(party_rows, start=1):
        # reuse dispute start span
        row = c.execute(
            "SELECT start_time_id, query_from, query_to, open_ended FROM disputed_region WHERE id=?",
            (did,),
        ).fetchone()
        start_id, qf, qt, oe = row
        pid = f"dispute_party.{i:03d}"
        c.execute(
            """
            INSERT INTO dispute_party(
              id, disputed_region_id, actor_id, role, claim_status,
              start_time_id, end_time_id, end_inclusive, open_ended, query_from, query_to
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, 1, ?, ?, ?)
            """,
            (pid, did, aid, role, claim, start_id, oe, qf, qt),
        )
        b.name(
            "dispute_party",
            pid,
            "ja" if aid in {"actor.japan", "actor.ryukyu_kingdom"} else "zh_hans",
            party_name,
            party_actor_id=aid,
            is_primary=1,
        )

    # Ryukyu milestones
    milestones = [
        ("dispute.ryukyu", "status_change", 1609, 1, 1, "萨摩入侵，双重从属开始（年到年骨架，日待校）"),
        ("dispute.ryukyu", "status_change", 1879, 1, 1, "琉球处分，冲绳县设置（年到年骨架）"),
        ("dispute.ryukyu", "occupation_begins", 1945, 1, 1, "美军接管开始（年到年骨架）"),
        ("dispute.ryukyu", "occupation_ends", 1972, 5, 15, "施政权返还"),
    ]
    for i, (did, kind, y, m, d, note) in enumerate(milestones, start=1):
        if kind == "occupation_ends":
            tp = b.day_point(y, m, d, id_hint=f"dispute.ryukyu.ms.{i}")
        else:
            tp, _, _, _, _ = b.span_from_years(y, y, id_prefix=f"dispute.ryukyu.ms.{i}")
        c.execute(
            """
            INSERT INTO dispute_milestone(
              id, disputed_region_id, kind, time_point_id, note
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (f"dispute_milestone.ryukyu.{i}", did, kind, tp, note),
        )

    # Integrity: bind modern era source
    c.execute(
        """
        INSERT INTO source_binding(
          id, object_kind, object_id, source_id, role, summary, is_primary
        ) VALUES
        ('bind.era.meiji', 'era_name', 'era.meiji', 'source.wikipedia_ja.era_names',
         'fact_spine', '明治年号端点', 1),
        ('bind.era.keicho', 'era_name', 'era.keicho', 'source.wikipedia_ja.era_names',
         'fact_spine', '庆长年号样例', 1),
        ('bind.period.jomon', 'period', 'period.jomon', 'source.wikipedia_ja.history_of_japan',
         'fact_spine', '绳文章节骨架', 1),
        ('bind.dispute.ryukyu', 'disputed_region', 'dispute.ryukyu', 'source.design.doc',
         'fact_spine', '产品要求将琉球列入争议地区表', 1)
        """
    )

    # Wikipedia-derived Kofun burial / construction horizons (not excavation years).
    from seed_kofun_burials import seed_into as seed_kofun_into

    n_kofun = seed_kofun_into(b)
    print(f"seeded kofun tombs: {n_kofun}")


def verify(conn: sqlite3.Connection) -> None:
    tables = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()[0]
    periods = conn.execute("SELECT COUNT(*) FROM period").fetchone()[0]
    disputes = conn.execute("SELECT COUNT(*) FROM disputed_region").fetchone()[0]
    eras = conn.execute("SELECT COUNT(*) FROM era_name").fetchone()[0]
    default_sc = conn.execute(
        "SELECT id FROM scenario WHERE is_default=1"
    ).fetchone()
    assert default_sc and default_sc[0] == "scenario.wikipedia_ja"
    assert disputes >= 4
    print(f"tables={tables} periods={periods} disputes={disputes} era_names={eras}")
    print("default_scenario=", default_sc[0])
    # sample query: eras covering 2019-05-01
    d = ordinal(2019, 5, 1)
    rows = conn.execute(
        """
        SELECT id FROM era_name
        WHERE chronology_track_id='chronology.japan_official'
          AND query_from <= ? AND query_to >= ?
        """,
        (d, d),
    ).fetchall()
    print("japan era on 2019-05-01:", [r[0] for r in rows])
    rows = conn.execute(
        """
        SELECT id FROM disputed_region
        WHERE query_from <= ? AND query_to >= ? AND status='active'
        ORDER BY id
        """,
        (d, d),
    ).fetchall()
    print("active disputes today-sample:", [r[0] for r in rows])


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        b = Builder(conn)
        b.exec_script(SCHEMA.read_text(encoding="utf-8"))
        seed(b)
        conn.commit()
        verify(conn)
        print(f"wrote {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
