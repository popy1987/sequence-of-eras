#!/usr/bin/env python3
"""
Build MVP sankin-kōtai routes (Satsuma + Kaga) on CODH Edo road/post geometry.

Downloads:
  - https://geoshape.ex.nii.ac.jp/edo/post/post.geojson  (CC BY)
  - per-road GeoJSON under https://geoshape.ex.nii.ac.jp/edo/road/{id}/

Outputs:
  web/data/edo_roads_subset.geojson   — road underlay for route-related IDs
  web/data/sankin_routes.json         — two sourced routes + stop props
  db/data/sankin_routes.json          — same
"""
from __future__ import annotations

import json
import math
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "db" / "data" / "_codh_cache"
WEB = ROOT / "web" / "data"
DB_OUT = Path(__file__).resolve().parent / "sankin_routes.json"
WEB_ROUTES = WEB / "sankin_routes.json"
WEB_ROADS = WEB / "edo_roads_subset.geojson"

POST_URL = "https://geoshape.ex.nii.ac.jp/edo/post/post.geojson"
ROAD_IDS = ["R001", "R002", "R400", "R506", "R600", "R700", "R900", "R901"]

# CODH 无同名宿场时，用同路邻近宿（史料名仍写在 needle）。
STOP_ALIASES = {
    "瀬高": ["原町"],  # 南関–羽犬塚间；CODH 无瀬高
    "岩国": ["関戸"],  # 西国街道岩国近傍
    "福山": ["神辺"],  # 福山城下近傍；R700 无「福山」宿名（R902 为萨摩同名）
    "明石": ["大蔵谷"],  # 明石近傍
    "大阪": ["大坂", "大坂京橋"],
    "直江津": ["長浜", "岩木"],  # 直江津港近傍；CODH 无直江津
}

# Ordered stop name needles (matched against CODH post name fields).
# Direction: castle → Edo.
SATSUMA_STOPS = [
    "鹿児島",
    "伊集院",
    "市来",
    "串木野",
    "向田",
    "阿久根",
    "出水",
    "陳町",
    "佐敷",
    "日奈久",
    "八代",
    "小川",
    "宇土",
    "河尻",
    "熊本",
    "山鹿",
    "南関",
    "瀬高",
    "羽犬塚",
    "府中",
    "松崎",
    "山家",
    "小倉",
    "赤間関",
    "徳山",
    "岩国",
    "広島",
    "三原",
    "尾道",
    "福山",
    "岡山",
    "姫路",
    "明石",
    "西宮",
    "大阪",
    "伏見",
    "京都",
    "大津",
    "草津",
    "土山",
    "関",
    "四日市",
    "桑名",
    "宮",
    "岡崎",
    "浜松",
    "掛川",
    "府中",
    "三島",
    "箱根",
    "小田原",
    "藤沢",
    "神奈川",
    "品川",
    "日本橋",
]

KAGA_STOPS = [
    "金沢",
    "高岡",
    "滑川",
    "魚津",
    "泊",
    "市振",
    "糸魚川",
    "直江津",
    "高田",
    "関川",
    "牟礼",
    "善光寺",
    "上田",
    "岩村田",
    "追分",
    "軽井沢",
    "坂本",
    "安中",
    "高崎",
    "本庄",
    "熊谷",
    "大宮",
    "板橋",
    "日本橋",
]


def fetch(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    print("download", url)
    req = urllib.request.Request(url, headers={"User-Agent": "sequence-of-eras/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        dest.write_bytes(r.read())
    return dest


def road_geojson_url(road_id: str) -> str:
    # Prefer explicit geojson if present; else directory page listing.
    return f"https://geoshape.ex.nii.ac.jp/edo/road/{road_id}/{road_id}.geojson"


def load_posts() -> list[dict]:
    path = fetch(POST_URL, CACHE / "post.geojson")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("features") or []


def post_names(feat: dict) -> list[str]:
    p = feat.get("properties") or {}
    names = []
    for key in ("name", "jk"):
        v = p.get(key)
        if isinstance(v, str) and v.strip():
            names.append(v.strip())
            # also bare kanji before parenthesis in jk: 日本橋（にほんばし）
            m = re.match(r"^([^\（\(]+)", v.strip())
            if m:
                names.append(m.group(1).strip())
    out, seen = [], set()
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def post_xy(feat: dict) -> tuple[float, float] | None:
    g = feat.get("geometry") or {}
    if g.get("type") == "Point":
        c = g.get("coordinates")
        if c and len(c) >= 2:
            return float(c[0]), float(c[1])
    return None


def road_ids_of(feat: dict) -> list[str]:
    p = feat.get("properties") or {}
    v = p.get("road_id")
    if isinstance(v, str) and v.startswith("R"):
        return [v.split("-")[0]]
    return []


def name_hit(needle: str, names: list[str]) -> tuple[bool, int]:
    """Avoid short-substring traps (関 ⊂ 下関)."""
    best = 0
    for n in names:
        if n == needle:
            best = max(best, 100)
        elif n.startswith(needle) or (needle.startswith(n) and len(n) >= 2 and len(needle) - len(n) <= 1):
            best = max(best, 80)
        elif needle in n and len(needle) >= 2:
            best = max(best, 50 + len(needle))
    return best > 0, best


def match_stop(
    needle: str,
    posts: list[dict],
    prefer_roads: set[str] | None = None,
    near: tuple[float, float] | None = None,
    query: str | None = None,
) -> dict | None:
    needle = needle.strip()
    q = (query or needle).strip()
    cands = []
    for f in posts:
        names = post_names(f)
        xy = post_xy(f)
        if not xy or not names:
            continue
        hit, base = name_hit(q, names)
        if not hit:
            continue
        roads = set(road_ids_of(f))
        score = float(base)
        if prefer_roads:
            if roads & prefer_roads:
                score += 40
            elif roads:
                score -= 15
        if near:
            score -= haversine_km(near, xy) / 20.0
        primary = next((n for n in names if n == q or q in n), names[0])
        cands.append((score, f, primary, xy, roads))
    if not cands:
        return None
    cands.sort(key=lambda x: -x[0])
    _score, f, name, xy, roads = cands[0]
    return {
        "name": name,
        "needle": needle,
        "lon": xy[0],
        "lat": xy[1],
        "roads": sorted(roads),
        "properties": f.get("properties") or {},
        "alias_of": None if q == needle else q,
    }


def haversine_km(a, b) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def resolve_stops(needles: list[str], posts: list[dict], prefer_roads: list[str]) -> list[dict]:
    pref = set(prefer_roads)
    out = []
    used = set()
    for needle in needles:
        local_pref = set(pref)
        if needle == "府中" and any(s["needle"] == "山家" for s in out):
            local_pref = {"R001"}
        elif needle == "府中":
            local_pref = {"R901", "R900"}
        elif needle in ("下関", "赤間関"):
            local_pref = {"R700", "R900"}
        elif needle == "直江津":
            local_pref = {"R400", "R506"}
        elif needle == "伏見":
            local_pref = {"R001", "R700", "R600"}
        elif needle == "大阪":
            local_pref = {"R601", "R600", "R700", "R001"}
        elif needle == "関":
            local_pref = {"R001"}
        elif needle == "福山":
            local_pref = {"R700"}
        near = (out[-1]["lon"], out[-1]["lat"]) if out else None
        queries = [needle] + STOP_ALIASES.get(needle, [])
        m = None
        for q in queries:
            cand = match_stop(needle, posts, local_pref, near=near, query=q)
            if not cand:
                continue
            if out:
                d = haversine_km((out[-1]["lon"], out[-1]["lat"]), (cand["lon"], cand["lat"]))
                if d > 180:
                    print(f"  reject jump {d:.0f}km: {needle}/{q} -> {cand['name']}")
                    continue
            m = cand
            break
        if not m:
            print(f"  miss stop: {needle}")
            continue
        key = (round(m["lon"], 4), round(m["lat"], 4))
        if key in used:
            print(f"  skip dup: {needle} -> {m['name']}")
            continue
        used.add(key)
        out.append(m)
        alias = f" via {m['alias_of']}" if m.get("alias_of") else ""
        print(f"  + {needle:6s} -> {m['name']}{alias} ({m['lon']:.3f},{m['lat']:.3f})")
    return out


def line_from_stops(stops: list[dict]) -> dict:
    coords = [[s["lon"], s["lat"]] for s in stops]
    length = 0.0
    for i in range(1, len(coords)):
        length += haversine_km(coords[i - 1], coords[i])
    return {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "LineString", "coordinates": coords},
        "_length_km": round(length, 1),
    }


def simplify_coords(coords: list, tol_deg: float = 0.002) -> list:
    """Douglas-Peucker-ish light decimate by spacing."""
    if len(coords) < 3:
        return coords
    out = [coords[0]]
    for c in coords[1:-1]:
        prev = out[-1]
        if abs(c[0] - prev[0]) + abs(c[1] - prev[1]) >= tol_deg:
            out.append(c)
    out.append(coords[-1])
    return out


def load_roads_subset() -> dict:
    features = []
    for rid in ROAD_IDS:
        # try several URL patterns
        candidates = [
            f"https://geoshape.ex.nii.ac.jp/edo/road/{rid}/{rid}.geojson",
            f"https://geoshape.ex.nii.ac.jp/edo/road/{rid}/road.geojson",
            f"https://geoshape.ex.nii.ac.jp/edo/road/{rid}.geojson",
        ]
        data = None
        dest = CACHE / f"road_{rid}.geojson"
        if dest.exists() and dest.stat().st_size > 1000:
            try:
                data = json.loads(dest.read_text(encoding="utf-8"))
            except Exception:
                dest.unlink(missing_ok=True)
                data = None
        for url in candidates:
            if data:
                break
            try:
                path = fetch(url, dest)
                data = json.loads(path.read_text(encoding="utf-8"))
                break
            except Exception as e:
                print("  road try fail", rid, url, type(e).__name__)
                if dest.exists():
                    dest.unlink()
        if not data:
            # scrape directory for .geojson
            try:
                html = urllib.request.urlopen(
                    f"https://geoshape.ex.nii.ac.jp/edo/road/{rid}/", timeout=30
                ).read().decode("utf-8", "replace")
                hrefs = re.findall(r'href="([^"]+\.geojson)"', html)
                if hrefs:
                    h = hrefs[0]
                    url = h if h.startswith("http") else f"https://geoshape.ex.nii.ac.jp/edo/road/{rid}/{h}"
                    path = fetch(url, CACHE / f"road_{rid}.geojson")
                    data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                print("  road dir fail", rid, e)
                continue
        feats = data.get("features") if isinstance(data, dict) else None
        if feats is None and data.get("type") == "Feature":
            feats = [data]
        if not feats:
            print("  empty road", rid)
            continue
        for f in feats:
            g = f.get("geometry") or {}
            props = dict(f.get("properties") or {})
            props["road_id"] = rid
            if g.get("type") == "LineString":
                g = {
                    "type": "LineString",
                    "coordinates": simplify_coords(g["coordinates"]),
                }
            elif g.get("type") == "MultiLineString":
                g = {
                    "type": "MultiLineString",
                    "coordinates": [simplify_coords(part) for part in g["coordinates"]],
                }
            features.append({"type": "Feature", "properties": props, "geometry": g})
        print(f"road {rid}: {len(feats)} features")
    return {"type": "FeatureCollection", "features": features}


def build_route(route_id, names, domain, stops_needles, prefer_roads, posts, note, sources):
    print(f"\n== {route_id} ==")
    stops = resolve_stops(stops_needles, posts, prefer_roads)
    geom_feat = line_from_stops(stops)
    return {
        "id": route_id,
        "kind": "sankin_kotai",
        "quality": "sourced_stops",
        "alignment": "approximate",
        "names": names,
        "domain": domain,
        "from_year": 1635,
        "to_year": 1862,
        "prefer_roads": prefer_roads,
        "note": note,
        "sources": sources,
        "length_km_approx": geom_feat["_length_km"],
        "stops": [
            {
                "name": s["name"],
                "needle": s["needle"],
                "lon": s["lon"],
                "lat": s["lat"],
                **({"alias_of": s["alias_of"]} if s.get("alias_of") else {}),
            }
            for s in stops
        ],
        "geometry": geom_feat["geometry"],
    }


def inspect_post_schema(posts: list[dict]):
    if not posts:
        return
    p = posts[0].get("properties") or {}
    print("post property keys sample:", sorted(p.keys())[:40])
    print("post sample props:", {k: p[k] for k in list(p)[:12]})


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    WEB.mkdir(parents=True, exist_ok=True)

    posts = load_posts()
    print("posts", len(posts))
    inspect_post_schema(posts)

    roads = load_roads_subset()
    WEB_ROADS.write_text(
        json.dumps(roads, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print("wrote", WEB_ROADS, "features", len(roads["features"]))

    routes = [
        build_route(
            "sankin.satsuma.izumi_saigoku_tokaido",
            {
                "zh_hans": "萨摩藩 · 出水筋→西国→东海道（示意）",
                "ja": "薩摩藩・出水筋→西国→東海道（示意）",
                "en": "Satsuma: Izumi → Saigoku → Tōkaidō",
            },
            {
                "id": "domain.satsuma",
                "names": {"zh_hans": "萨摩藩", "ja": "薩摩藩", "en": "Satsuma"},
                "castle": {"lon": 130.554, "lat": 31.599, "names": {"zh_hans": "鹿儿岛城", "ja": "鹿児島城", "en": "Kagoshima Castle"}},
            },
            SATSUMA_STOPS,
            ["R901", "R900", "R700", "R001"],
            posts,
            "以岛津齐彬嘉永参府公开叙述为骨架（出水筋→小仓→下关→西国街道→东海道→江户）。宿次用 CODH 宿场坐标串联，非逐里实测轨迹。",
            [
                {
                    "title": "nippon.com 参勤交代日程・ルート",
                    "url": "https://www.nippon.com/ja/articles/-/3023",
                },
                {
                    "title": "Wikipedia 薩摩街道（出水筋宿次）",
                    "url": "https://ja.wikipedia.org/wiki/%E8%96%A9%E6%91%A9%E8%A1%97%E9%81%93",
                },
                {
                    "title": "CODH 江戸宿場・主要街道データセット (CC BY 4.0)",
                    "url": "https://codh.rois.ac.jp/historical-gis/edo-road/",
                },
            ],
        ),
        build_route(
            "sankin.kaga.hokkoku_shimo_nakasendo",
            {
                "zh_hans": "加贺藩 · 北国下街道→中山道（示意）",
                "ja": "加賀藩・北国下街道→中山道（示意）",
                "en": "Kaga: Hokkoku-shimo → Nakasendō",
            },
            {
                "id": "domain.kaga",
                "names": {"zh_hans": "加贺藩", "ja": "加賀藩", "en": "Kaga"},
                "castle": {"lon": 136.625, "lat": 36.566, "names": {"zh_hans": "金泽城", "ja": "金沢城", "en": "Kanazawa Castle"}},
            },
            KAGA_STOPS,
            ["R400", "R506", "R002"],
            posts,
            "加贺藩主用下街道：金泽→越中→越后→追分入中山道→板桥→江户。约 480km／12–15 日量级。宿次串联 CODH 坐标；上街道／东海道变体未收入本条。",
            [
                {
                    "title": "板橋区 加賀藩参勤交代と北国街道",
                    "url": "https://www.city.itabashi.tokyo.jp/bunka/bunkazi/jidai/1004880.html",
                },
                {
                    "title": "加賀藩の参勤交代と北国街道",
                    "url": "http://www.i-shigaken.com/kikou/yukari/yukari11.html",
                },
                {
                    "title": "CODH 江戸宿場・主要街道データセット (CC BY 4.0)",
                    "url": "https://codh.rois.ac.jp/historical-gis/edo-road/",
                },
            ],
        ),
    ]

    doc = {
        "meta": {
            "version": "0.1.0",
            "note": "参勤交代史料级试点：萨摩・加贺。路线为宿场点折线示意，底图街道来自 CODH（CC BY 4.0）。",
            "attribution": "江戸主要街道・宿場データセット（ROIS-DS CODH）CC BY 4.0",
            "year_min": 1635,
            "year_max": 1862,
        },
        "routes": routes,
    }
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    DB_OUT.write_text(text + "\n", encoding="utf-8")
    WEB_ROUTES.write_text(text + "\n", encoding="utf-8")
    print("wrote", DB_OUT)
    print("wrote", WEB_ROUTES)
    for r in routes:
        print(r["id"], "stops", len(r["stops"]), "km~", r["length_km_approx"])


if __name__ == "__main__":
    main()
