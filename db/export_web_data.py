#!/usr/bin/env python3
"""Export SQLite seed + schematic territory phases to web/data/atlas.json."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "sequence_of_eras.sqlite"
OUT = ROOT / "web" / "data" / "atlas.json"
OPEN_TO = 2_147_483_647


def to_jdn(year: int, month: int, day: int) -> int:
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


EPOCH_JDN = to_jdn(-200_000, 1, 1)


def ordinal(year: int, month: int = 7, day: int = 1) -> int:
    return to_jdn(year, month, day) - EPOCH_JDN


def names_for(conn: sqlite3.Connection, kind: str, oid: str) -> dict:
    rows = conn.execute(
        """
        SELECT language, text FROM name_record
        WHERE object_kind=? AND object_id=? AND is_primary=1
        """,
        (kind, oid),
    ).fetchall()
    return {lang: text for lang, text in rows}


# Simplified Japan land outlines (schematic, WGS84). Enough to read as the archipelago.
JAPAN_LAND = {
    "type": "MultiPolygon",
    "coordinates": [
        # Hokkaido
        [[[139.4, 41.4], [141.6, 41.5], [145.8, 43.2], [145.5, 44.5], [144.0, 45.5],
          [141.9, 45.4], [140.0, 42.6], [139.4, 41.4]]],
        # Honshu
        [[[130.9, 34.0], [131.5, 33.6], [133.0, 33.4], [134.7, 33.5], [135.8, 33.4],
          [136.9, 34.6], [137.5, 34.7], [138.9, 34.6], [139.8, 35.1], [140.9, 35.7],
          [140.9, 36.9], [141.0, 38.3], [141.6, 39.0], [141.9, 40.5], [141.4, 41.4],
          [140.3, 41.5], [139.7, 40.5], [139.8, 39.0], [139.5, 38.2], [138.2, 37.2],
          [137.0, 36.8], [136.0, 36.2], [135.0, 35.7], [134.0, 35.6], [132.5, 35.4],
          [131.2, 34.8], [130.9, 34.0]]],
        # Shikoku
        [[[132.3, 32.9], [134.4, 33.0], [134.7, 34.0], [133.8, 34.4], [132.8, 34.0],
          [132.1, 33.5], [132.3, 32.9]]],
        # Kyushu
        [[[129.7, 31.2], [131.2, 31.0], [132.0, 31.8], [131.9, 33.2], [130.9, 33.9],
          [129.8, 33.3], [129.5, 32.5], [129.7, 31.2]]],
        # Okinawa main
        [[[127.6, 26.0], [128.3, 26.1], [128.3, 26.9], [127.7, 26.8], [127.6, 26.0]]],
    ],
}


def ring(*pts):
    """Return one LinearRing: [[lon, lat], ...]."""
    pts = [list(p) for p in pts]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def poly(*rings_pts):
    """Build a Polygon from one or more rings passed as point lists."""
    return {"type": "Polygon", "coordinates": [ring(*r) for r in rings_pts]}


# Regional building blocks (schematic polygons)
REGIONS = {
    "hokkaido": poly([(139.5, 41.5), (145.5, 43.0), (145.2, 45.3), (141.5, 45.2), (140.0, 42.7)]),
    "tohoku": poly([(139.5, 37.5), (141.5, 38.0), (141.8, 41.3), (140.2, 41.4), (139.5, 39.0)]),
    "kanto": poly([(138.8, 35.0), (140.9, 35.2), (140.9, 37.0), (139.2, 37.0)]),
    "chubu": poly([(136.0, 34.7), (138.9, 34.7), (139.0, 37.0), (136.5, 36.8)]),
    "kinki": poly([(134.5, 33.6), (136.5, 34.0), (136.5, 35.6), (134.8, 35.5)]),
    "chugoku": poly([(130.9, 33.9), (134.5, 33.8), (134.5, 35.5), (132.0, 35.3)]),
    "shikoku": poly([(132.3, 32.9), (134.5, 33.0), (134.6, 34.2), (132.8, 34.0)]),
    "kyushu": poly([(129.7, 31.2), (131.8, 31.2), (131.9, 33.6), (129.8, 33.2)]),
    "okinawa": poly([(127.5, 26.0), (128.4, 26.0), (128.4, 26.9), (127.5, 26.8)]),
    "kinai_core": poly([(135.0, 34.2), (136.2, 34.4), (136.2, 35.2), (135.2, 35.1)]),
    "west_honshu_yayoi": poly([(130.9, 33.5), (135.5, 34.0), (135.5, 35.3), (131.5, 34.8)]),
    "yamato_kofun": poly([(131.0, 33.5), (140.5, 35.0), (140.5, 36.5), (136.0, 36.0), (131.5, 34.8)]),
    "emishi": poly([(139.5, 38.0), (141.7, 38.5), (141.8, 41.3), (140.0, 41.2)]),
    "hayato": poly([(130.5, 31.1), (131.8, 31.1), (131.8, 32.4), (130.5, 32.3)]),
    "jomon_east": poly([(136.0, 34.5), (141.5, 35.5), (141.5, 41.0), (139.0, 41.0), (136.0, 37.0)]),
    "jomon_west": poly([(129.8, 31.5), (135.5, 33.5), (135.5, 35.5), (130.5, 34.5)]),
    "satsuma": poly([(130.0, 31.1), (131.5, 31.1), (131.5, 32.4), (130.0, 32.3)]),
    "shimazu_kyushu": poly([(129.8, 31.1), (131.9, 31.2), (131.8, 32.8), (129.9, 32.5)]),
    "mori": poly([(130.9, 33.8), (133.5, 34.0), (133.5, 35.2), (131.5, 34.9)]),
    "oda": poly([(135.5, 34.5), (137.2, 34.7), (137.2, 35.6), (135.6, 35.5)]),
    "takeda": poly([(137.8, 35.2), (139.0, 35.3), (139.0, 36.5), (137.8, 36.4)]),
    "uesugi": poly([(138.0, 36.5), (139.8, 36.8), (139.8, 38.2), (138.0, 37.8)]),
    "hojo": poly([(138.9, 34.8), (140.2, 35.0), (140.2, 36.0), (139.0, 35.9)]),
    "date": poly([(140.2, 37.5), (141.7, 38.0), (141.6, 39.5), (140.3, 39.0)]),
    "imagawa": poly([(137.5, 34.6), (139.0, 34.7), (139.0, 35.4), (137.6, 35.3)]),
}


def polity(pid, names, color, region_keys, mode="direct"):
    coords = []
    for key in region_keys:
        g = REGIONS[key]
        coords.append(g["coordinates"][0])
    geom = {"type": "MultiPolygon", "coordinates": [[c] for c in coords]} if len(coords) > 1 else {
        "type": "Polygon", "coordinates": [coords[0]]
    }
    return {
        "id": pid,
        "names": names,
        "color": color,
        "mode": mode,
        "geometry": geom,
    }


# Schematic territory phases. Boundaries are illustrative, not surveyed.
PHASES = [
    {
        "id": "phase.paleolithic",
        "from_year": -38000,
        "to_year": -14000,
        "label": {"zh_hans": "旧石器 · 遗迹点", "ja": "旧石器", "en": "Paleolithic"},
        "polities": [],
        "markers": [
            {"id": "site.iwajuku", "lon": 139.33, "lat": 36.4, "names": {"zh_hans": "岩宿", "ja": "岩宿", "en": "Iwajuku"}, "kind": "site"},
            {"id": "site.ishinomoto", "lon": 130.7, "lat": 32.8, "names": {"zh_hans": "石の本一带", "ja": "石の本", "en": "Ishinomoto area"}, "kind": "site"},
        ],
        "note": "默认不画政权面，只显示遗迹级标记。",
    },
    {
        "id": "phase.jomon",
        "from_year": -14000,
        "to_year": -400,
        "label": {"zh_hans": "绳文文化分布（示意）", "ja": "縄文", "en": "Jōmon"},
        "polities": [
            polity("culture.jomon_east", {"zh_hans": "绳文（东）", "ja": "縄文（東）", "en": "Jōmon East"}, "#6b8f71", ["jomon_east"], "cultural"),
            polity("culture.jomon_west", {"zh_hans": "绳文（西）", "ja": "縄文（西）", "en": "Jōmon West"}, "#8fae7e", ["jomon_west"], "cultural"),
        ],
        "markers": [
            {"id": "site.sannai", "lon": 140.7, "lat": 40.8, "names": {"zh_hans": "三内丸山", "ja": "三内丸山", "en": "Sannai-Maruyama"}, "kind": "site"},
        ],
        "note": "文化分布示意，不是国界。约公元前 2000 年可与中国夏商周对照观看，日本列岛此时考古材料仍稀少。",
    },
    {
        "id": "phase.yayoi",
        "from_year": -400,
        "to_year": 250,
        "label": {"zh_hans": "弥生 · 稻作与区域势力", "ja": "弥生", "en": "Yayoi"},
        "polities": [
            polity("culture.yayoi_core", {"zh_hans": "弥生文化核心", "ja": "弥生文化", "en": "Yayoi core"}, "#c4a35a", ["west_honshu_yayoi", "kyushu", "shikoku", "kinki"], "cultural"),
        ],
        "markers": [
            {"id": "site.yoshinogari", "lon": 130.3, "lat": 33.3, "names": {"zh_hans": "吉野ヶ里", "ja": "吉野ヶ里", "en": "Yoshinogari"}, "kind": "site"},
        ],
        "note": "邪马台国位置有争议，默认不画唯一国界。",
    },
    {
        "id": "phase.kofun",
        "from_year": 250,
        "to_year": 592,
        "label": {"zh_hans": "古坟 · 大和扩展", "ja": "古墳", "en": "Kofun"},
        "polities": [
            polity("actor.yamato", {"zh_hans": "大和政权", "ja": "ヤマト王権", "en": "Yamato"}, "#2f5d8c", ["yamato_kofun", "kinki", "chugoku", "shikoku", "kyushu"], "approximate"),
            polity("actor.emishi", {"zh_hans": "虾夷活动区", "ja": "蝦夷", "en": "Emishi"}, "#7a8b6f", ["emishi"], "sphere"),
            polity("actor.hayato", {"zh_hans": "隼人", "ja": "隼人", "en": "Hayato"}, "#9a6b4a", ["hayato"], "sphere"),
        ],
        "markers": [
            {"id": "place.nara_basin", "lon": 135.8, "lat": 34.5, "names": {"zh_hans": "大和盆地", "ja": "大和盆地", "en": "Nara Basin"}, "kind": "capital"},
        ],
        "note": "边界为示意扩展带。",
    },
    {
        "id": "phase.asuka_nara",
        "from_year": 592,
        "to_year": 794,
        "label": {"zh_hans": "飞鸟—奈良 · 律令国家", "ja": "飛鳥・奈良", "en": "Asuka–Nara"},
        "polities": [
            polity("actor.ritsuryo", {"zh_hans": "律令国家", "ja": "律令国家", "en": "Ritsuryō state"}, "#355c7d", ["kyushu", "shikoku", "chugoku", "kinki", "chubu", "kanto"], "administered"),
            polity("actor.emishi", {"zh_hans": "虾夷边疆", "ja": "蝦夷", "en": "Emishi frontier"}, "#7a8b6f", ["tohoku"], "contested"),
        ],
        "markers": [
            {"id": "place.fujiwarakyo", "lon": 135.8, "lat": 34.5, "names": {"zh_hans": "藤原京", "ja": "藤原京", "en": "Fujiwara-kyō"}, "kind": "capital"},
            {"id": "place.heijokyo", "lon": 135.8, "lat": 34.69, "names": {"zh_hans": "平城京", "ja": "平城京", "en": "Heijō-kyō"}, "kind": "capital"},
        ],
        "note": "北海道尚未纳入令制国。",
    },
    {
        "id": "phase.heian",
        "from_year": 794,
        "to_year": 1185,
        "label": {"zh_hans": "平安", "ja": "平安", "en": "Heian"},
        "polities": [
            polity("actor.heian_court", {"zh_hans": "平安朝廷支配域", "ja": "朝廷", "en": "Heian court"}, "#3d5a80", ["kyushu", "shikoku", "chugoku", "kinki", "chubu", "kanto", "tohoku"], "administered"),
        ],
        "markers": [
            {"id": "place.heiankyo", "lon": 135.77, "lat": 35.01, "names": {"zh_hans": "平安京", "ja": "平安京", "en": "Heian-kyō"}, "kind": "capital"},
        ],
        "note": "东北边疆仍在变动。",
    },
    {
        "id": "phase.kamakura",
        "from_year": 1185,
        "to_year": 1333,
        "label": {"zh_hans": "镰仓幕府", "ja": "鎌倉", "en": "Kamakura"},
        "polities": [
            polity("actor.kamakura", {"zh_hans": "镰仓幕府", "ja": "鎌倉幕府", "en": "Kamakura shogunate"}, "#4a6741", ["kyushu", "shikoku", "chugoku", "kinki", "chubu", "kanto", "tohoku"], "direct"),
            polity("actor.court", {"zh_hans": "朝廷（名义）", "ja": "朝廷", "en": "Imperial court"}, "#8b7355", ["kinai_core"], "nominal"),
        ],
        "markers": [
            {"id": "place.kamakura", "lon": 139.55, "lat": 35.32, "names": {"zh_hans": "镰仓", "ja": "鎌倉", "en": "Kamakura"}, "kind": "capital"},
            {"id": "place.kyoto", "lon": 135.77, "lat": 35.01, "names": {"zh_hans": "京都", "ja": "京都", "en": "Kyoto"}, "kind": "capital"},
        ],
        "note": "朝廷名义与幕府实控并存。",
    },
    {
        "id": "phase.muromachi",
        "from_year": 1336,
        "to_year": 1467,
        "label": {"zh_hans": "室町", "ja": "室町", "en": "Muromachi"},
        "polities": [
            polity("actor.ashikaga", {"zh_hans": "室町幕府", "ja": "室町幕府", "en": "Ashikaga shogunate"}, "#5c6b73", ["kyushu", "shikoku", "chugoku", "kinki", "chubu", "kanto", "tohoku"], "delegated"),
            polity("actor.ryukyu", {"zh_hans": "琉球（古斯库/三山）", "ja": "琉球", "en": "Ryukyu"}, "#c17f59", ["okinawa"], "direct"),
        ],
        "markers": [
            {"id": "place.kyoto", "lon": 135.77, "lat": 35.01, "names": {"zh_hans": "京都", "ja": "京都", "en": "Kyoto"}, "kind": "capital"},
        ],
        "note": "守护分权，后期进入战国。",
    },
    {
        "id": "phase.sengoku",
        "from_year": 1467,
        "to_year": 1573,
        "label": {"zh_hans": "战国并立", "ja": "戦国", "en": "Sengoku"},
        "polities": [
            polity("daimyo.oda", {"zh_hans": "织田", "ja": "織田", "en": "Oda"}, "#c0392b", ["oda"], "direct"),
            polity("daimyo.takeda", {"zh_hans": "武田", "ja": "武田", "en": "Takeda"}, "#8e44ad", ["takeda"], "direct"),
            polity("daimyo.uesugi", {"zh_hans": "上杉", "ja": "上杉", "en": "Uesugi"}, "#2980b9", ["uesugi"], "direct"),
            polity("daimyo.hojo", {"zh_hans": "后北条", "ja": "後北条", "en": "Hōjō"}, "#16a085", ["hojo"], "direct"),
            polity("daimyo.mori", {"zh_hans": "毛利", "ja": "毛利", "en": "Mōri"}, "#d35400", ["mori"], "direct"),
            polity("daimyo.shimazu", {"zh_hans": "岛津", "ja": "島津", "en": "Shimazu"}, "#2c3e50", ["shimazu_kyushu"], "direct"),
            polity("daimyo.date", {"zh_hans": "伊达", "ja": "伊達", "en": "Date"}, "#7f8c8d", ["date"], "direct"),
            polity("daimyo.imagawa", {"zh_hans": "今川", "ja": "今川", "en": "Imagawa"}, "#f39c12", ["imagawa"], "direct"),
            polity("actor.ryukyu", {"zh_hans": "琉球王国", "ja": "琉球王国", "en": "Ryukyu Kingdom"}, "#c17f59", ["okinawa"], "direct"),
        ],
        "markers": [],
        "note": "郡级势力的概略色块，非精确版图。",
    },
    {
        "id": "phase.azuchi",
        "from_year": 1573,
        "to_year": 1602,
        "label": {"zh_hans": "织丰统一进程", "ja": "安土桃山", "en": "Azuchi–Momoyama"},
        "polities": [
            polity("actor.toyotomi", {"zh_hans": "丰臣政权", "ja": "豊臣政権", "en": "Toyotomi"}, "#c0392b", ["kyushu", "shikoku", "chugoku", "kinki", "chubu", "kanto", "tohoku"], "direct"),
            polity("actor.tokugawa", {"zh_hans": "德川领", "ja": "徳川", "en": "Tokugawa"}, "#2c3e50", ["kanto"], "vassal"),
            polity("actor.ryukyu", {"zh_hans": "琉球王国", "ja": "琉球王国", "en": "Ryukyu Kingdom"}, "#c17f59", ["okinawa"], "direct"),
        ],
        "markers": [
            {"id": "place.azuchi", "lon": 136.14, "lat": 35.14, "names": {"zh_hans": "安土", "ja": "安土", "en": "Azuchi"}, "kind": "castle"},
            {"id": "place.osaka", "lon": 135.5, "lat": 34.68, "names": {"zh_hans": "大坂", "ja": "大坂", "en": "Osaka"}, "kind": "castle"},
        ],
        "note": "统一进程示意；北海道仍大体在幕藩体系外。",
    },
    {
        "id": "phase.edo",
        "from_year": 1603,
        "to_year": 1868,
        "label": {"zh_hans": "江户幕藩", "ja": "江戸", "en": "Edo"},
        "polities": [
            polity("actor.bakufu", {"zh_hans": "江户幕府支配域", "ja": "江戸幕府", "en": "Tokugawa bakufu"}, "#34495e", ["kyushu", "shikoku", "chugoku", "kinki", "chubu", "kanto", "tohoku"], "direct"),
            polity("actor.matsumae", {"zh_hans": "松前藩进出", "ja": "松前", "en": "Matsumae"}, "#7f8c8d", ["hokkaido"], "sphere"),
            polity("actor.ryukyu", {"zh_hans": "琉球（双重从属）", "ja": "琉球", "en": "Ryukyu (dual)"}, "#c17f59", ["okinawa"], "dual"),
        ],
        "markers": [
            {"id": "place.edo", "lon": 139.75, "lat": 35.68, "names": {"zh_hans": "江户", "ja": "江戸", "en": "Edo"}, "kind": "capital"},
            {"id": "place.kyoto", "lon": 135.77, "lat": 35.01, "names": {"zh_hans": "京都", "ja": "京都", "en": "Kyoto"}, "kind": "capital"},
        ],
        "note": "琉球对萨摩与明清双重从属，见争议地区卡片。",
    },
    {
        "id": "phase.meiji",
        "from_year": 1868,
        "to_year": 1912,
        "label": {"zh_hans": "明治国家", "ja": "明治", "en": "Meiji"},
        "polities": [
            polity("actor.japan", {"zh_hans": "大日本帝国（本土）", "ja": "日本", "en": "Japan"}, "#1f4e79", ["hokkaido", "tohoku", "kanto", "chubu", "kinki", "chugoku", "shikoku", "kyushu", "okinawa"], "direct"),
        ],
        "markers": [
            {"id": "place.tokyo", "lon": 139.75, "lat": 35.68, "names": {"zh_hans": "东京", "ja": "東京", "en": "Tokyo"}, "kind": "capital"},
        ],
        "note": "1879 年后冲绳县入图；境外控制另图层。",
    },
    {
        "id": "phase.modern",
        "from_year": 1912,
        "to_year": 2027,
        "label": {"zh_hans": "近现代日本", "ja": "近現代", "en": "Modern"},
        "polities": [
            polity("actor.japan", {"zh_hans": "日本国", "ja": "日本国", "en": "Japan"}, "#1f4e79", ["hokkaido", "tohoku", "kanto", "chubu", "kinki", "chugoku", "shikoku", "kyushu", "okinawa"], "direct"),
        ],
        "markers": [
            {"id": "place.tokyo", "lon": 139.75, "lat": 35.68, "names": {"zh_hans": "东京", "ja": "東京", "en": "Tokyo"}, "kind": "capital"},
        ],
        "note": "争议地区以独立图层标出，不作主权裁决。",
    },
]


def export() -> None:
    if not DB.exists():
        raise SystemExit(f"missing {DB}; run python db/build_db.py first")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    periods = []
    for row in conn.execute(
        """
        SELECT id, parent_id, kind, region_id, sort_order, query_from, query_to, open_ended
        FROM period
        WHERE scenario_id='scenario.wikipedia_ja'
        ORDER BY sort_order
        """
    ):
        names = names_for(conn, "period", row["id"])
        # approximate year from preferred midpoints stored in linked time points is heavy;
        # derive display years from sort seed already known via names + query ordinals is awkward.
        periods.append({
            "id": row["id"],
            "parent_id": row["parent_id"],
            "kind": row["kind"],
            "region_id": row["region_id"],
            "sort_order": row["sort_order"],
            "query_from": row["query_from"],
            "query_to": row["query_to"] if row["query_to"] != OPEN_TO else None,
            "open_ended": bool(row["open_ended"]),
            "names": names,
        })

    # Enrich periods with year hints from time_point preferred_year
    for p in periods:
        start = conn.execute(
            """
            SELECT preferred_year FROM time_point tp
            JOIN period pe ON pe.start_time_id = tp.id WHERE pe.id=?
            """,
            (p["id"],),
        ).fetchone()
        end = conn.execute(
            """
            SELECT preferred_year FROM time_point tp
            JOIN period pe ON pe.end_time_id = tp.id WHERE pe.id=?
            """,
            (p["id"],),
        ).fetchone()
        p["from_year"] = start["preferred_year"] if start else None
        p["to_year"] = end["preferred_year"] if end else None

    eras_japan = []
    for row in conn.execute(
        """
        SELECT e.id, e.query_from, e.query_to, e.open_ended, e.year_start_calendar,
               ts.preferred_year AS sy, ts.preferred_month AS sm, ts.preferred_day AS sd,
               te.preferred_year AS ey, te.preferred_month AS em, te.preferred_day AS ed
        FROM era_name e
        JOIN time_point ts ON ts.id = e.start_time_id
        LEFT JOIN time_point te ON te.id = e.end_time_id
        WHERE e.chronology_track_id='chronology.japan_official'
        ORDER BY e.query_from
        """
    ):
        eras_japan.append({
            "id": row["id"],
            "names": names_for(conn, "era_name", row["id"]),
            "from": {"year": row["sy"], "month": row["sm"], "day": row["sd"]},
            "to": None if row["open_ended"] else {"year": row["ey"], "month": row["em"], "day": row["ed"]},
            "query_from": row["query_from"],
            "query_to": None if row["open_ended"] else row["query_to"],
            "open_ended": bool(row["open_ended"]),
        })

    dynasties_china = []
    for row in conn.execute(
        """
        SELECT d.id, d.query_from, d.query_to, d.open_ended,
               ts.preferred_year AS sy, te.preferred_year AS ey
        FROM dynasty d
        JOIN time_point ts ON ts.id = d.start_time_id
        LEFT JOIN time_point te ON te.id = d.end_time_id
        WHERE d.chronology_track_id='chronology.china_main'
        ORDER BY d.query_from
        """
    ):
        dynasties_china.append({
            "id": row["id"],
            "names": names_for(conn, "dynasty", row["id"]),
            "from_year": row["sy"],
            "to_year": row["ey"],
            "query_from": row["query_from"],
            "query_to": None if row["open_ended"] else row["query_to"],
            "open_ended": bool(row["open_ended"]),
        })

    eras_china = []
    for row in conn.execute(
        """
        SELECT e.id, e.dynasty_id, e.query_from, e.query_to, e.open_ended,
               ts.preferred_year AS sy, te.preferred_year AS ey
        FROM era_name e
        JOIN time_point ts ON ts.id = e.start_time_id
        LEFT JOIN time_point te ON te.id = e.end_time_id
        WHERE e.chronology_track_id='chronology.china_main'
        ORDER BY e.query_from
        """
    ):
        eras_china.append({
            "id": row["id"],
            "dynasty_id": row["dynasty_id"],
            "names": names_for(conn, "era_name", row["id"]),
            "from_year": row["sy"],
            "to_year": row["ey"],
            "query_from": row["query_from"],
            "query_to": None if row["open_ended"] else row["query_to"],
            "open_ended": bool(row["open_ended"]),
        })

    disputes = []
    for row in conn.execute(
        "SELECT * FROM disputed_region ORDER BY id"
    ):
        parties = []
        for p in conn.execute(
            "SELECT * FROM dispute_party WHERE disputed_region_id=? ORDER BY id",
            (row["id"],),
        ):
            parties.append({
                "id": p["id"],
                "actor_id": p["actor_id"],
                "actor_names": names_for(conn, "actor", p["actor_id"]),
                "role": p["role"],
                "claim_status": p["claim_status"],
            })
        geom = None
        if row["geometry_id"]:
            g = conn.execute("SELECT geojson, label_lon, label_lat FROM geometry WHERE id=?", (row["geometry_id"],)).fetchone()
            if g:
                geom = {"geojson": json.loads(g["geojson"]), "lon": g["label_lon"], "lat": g["label_lat"]}
        disputes.append({
            "id": row["id"],
            "kind": row["kind"],
            "status": row["status"],
            "sensitivity": row["sensitivity"],
            "short_note": row["short_note"],
            "names": names_for(conn, "disputed_region", row["id"]),
            "parties": parties,
            "geometry": geom,
            "query_from": row["query_from"],
            "query_to": None if row["open_ended"] else row["query_to"],
            "open_ended": bool(row["open_ended"]),
        })

    layers = []
    for row in conn.execute("SELECT id, sort_order, default_on FROM map_layer ORDER BY sort_order"):
        layers.append({
            "id": row["id"],
            "sort_order": row["sort_order"],
            "default_on": bool(row["default_on"]),
            "names": names_for(conn, "map_layer", row["id"]),
        })

    # Kofun burial/construction markers from DB (築造时期 → burial horizon, not excavation).
    kofun_markers = []
    for row in conn.execute(
        """
        SELECT p.id, p.lon, p.lat,
               ts.preferred_year AS burial_from,
               te.preferred_year AS burial_to,
               ts.confidence AS confidence,
               n.body AS note
        FROM place p
        JOIN place_function pf ON pf.place_id = p.id AND pf.function_kind='site_occupation'
        JOIN time_point ts ON ts.id = pf.start_time_id
        JOIN time_point te ON te.id = pf.end_time_id
        LEFT JOIN note n ON n.object_id = p.id AND n.language='zh_hans'
        WHERE p.kind='kofun'
        ORDER BY (te.preferred_year - ts.preferred_year) ASC, p.id
        """
    ):
        if row["lon"] is None or row["lat"] is None:
            continue
        marker = {
            "id": row["id"],
            "lon": row["lon"],
            "lat": row["lat"],
            "names": names_for(conn, "place", row["id"]),
            "kind": "kofun",
            "burial_from": row["burial_from"],
            "burial_to": row["burial_to"],
            "confidence": row["confidence"],
        }
        if row["note"]:
            marker["note"] = row["note"]
        kofun_markers.append(marker)

    # Historical events (Asuka / Nara / Heian spine + wars).
    import re as _re

    events = []
    for row in conn.execute(
        """
        SELECT e.id, e.kind, e.importance, e.timeline_policy, e.short_note, e.alignment,
               e.query_from, e.query_to, e.open_ended,
               ts.preferred_year AS from_year,
               COALESCE(te.preferred_year, ts.preferred_year) AS to_year,
               g.label_lon AS lon, g.label_lat AS lat,
               mf.style_json
        FROM event e
        JOIN time_point ts ON ts.id = e.start_time_id
        LEFT JOIN time_point te ON te.id = e.end_time_id
        LEFT JOIN event_place ep ON ep.event_id = e.id AND ep.role='primary'
        LEFT JOIN geometry g ON g.id = ep.geometry_id
        LEFT JOIN map_feature mf ON mf.object_id = e.id AND mf.layer_id='layer.events'
        ORDER BY ts.preferred_year, e.importance, e.id
        """
    ):
        note = row["short_note"] or ""
        cc = None
        m = _re.search(r"\[conflict:([^\]]+)\]", note)
        if m:
            cc = m.group(1)
            note = _re.sub(r"\[conflict:[^\]]+\]\s*", "", note).strip()
        style = {}
        if row["style_json"]:
            try:
                style = json.loads(row["style_json"])
            except json.JSONDecodeError:
                style = {}
        if not cc:
            cc = style.get("conflict_class")
        item = {
            "id": row["id"],
            "kind": row["kind"],
            "conflict_class": cc,
            "importance": row["importance"],
            "timeline_policy": row["timeline_policy"],
            "alignment": row["alignment"],
            "from_year": row["from_year"],
            "to_year": row["to_year"],
            "names": names_for(conn, "event", row["id"]),
            "short_note": note,
            "query_from": row["query_from"],
            "query_to": None if row["open_ended"] else row["query_to"],
            "open_ended": bool(row["open_ended"]),
            "parent_id": style.get("parent_id"),
            "period": style.get("period"),
        }
        if row["lon"] is not None and row["lat"] is not None:
            item["lon"] = row["lon"]
            item["lat"] = row["lat"]
        events.append(item)

    # Phase markers stay schematic capitals only; kofun attach at runtime from kofun_burials.
    phases = [dict(ph) for ph in PHASES]
    for ph in phases:
        ph["query_from"] = ordinal(ph["from_year"], 1, 1)
        ph["query_to"] = ordinal(ph["to_year"], 12, 31)
        ph["markers"] = list(ph.get("markers") or [])

    atlas = {
        "meta": {
            "title": {"zh_hans": "时代序列 · 日本历史地图", "ja": "時代序列 · 日本歴史地図", "en": "Sequence of Eras"},
            "version": "0.1.3",
            "source_db": "db/sequence_of_eras.sqlite",
            "note": "疆域几何为示意复原；古坟为築造／埋入区间；飞鸟–平安事件含内战与平乱，争议年份用区间。",
            "year_min": -38000,
            "year_max": 2026,
            # Align first viewport with Xia–Shang–Zhou horizon (~2000 BCE).
            # Japan then is still Jōmon; sparse archaeology is expected.
            "default_year": -2000,
            "default_year_reason": "对齐中国夏商周年代视野；此时日本仍处绳文，考古证据稀少。",
            "kofun_burial_count": len(kofun_markers),
            "event_count": len(events),
        },
        "coastline": JAPAN_LAND,
        "periods": periods,
        "eras_japan": eras_japan,
        "dynasties_china": dynasties_china,
        "eras_china": eras_china,
        "disputes": disputes,
        "layers": layers,
        "phases": phases,
        "kofun_burials": kofun_markers,
        "events": events,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Compact JSON for faster first download (preview server may also gzip).
    payload = json.dumps(atlas, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(payload, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB compact)")
    wars = sum(1 for e in events if e.get("conflict_class"))
    print(
        f"phases={len(phases)} periods={len(periods)} disputes={len(disputes)} "
        f"kofun_burials={len(kofun_markers)} "
        f"events={len(events)} conflict_tagged={wars}"
    )
    conn.close()


if __name__ == "__main__":
    export()
