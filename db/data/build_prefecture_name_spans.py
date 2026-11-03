#!/usr/bin/env python3
"""Build schematic place-name spans per modern prefecture (考古→令制国→藩领示意→废藩置县→今名)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "prefecture_name_spans.json"
WEB_OUT = ROOT / "web" / "data" / "prefecture_name_spans.json"

# Modern pref → primary 令制国 (示意；一县多国时并列主国名)
PROVINCES: dict[str, dict] = {
    "JP-01": {
        "zh_hans": "虾夷地／阿伊努居住域（示意）",
        "ja": "蝦夷地・アイヌ居住域（示意）",
        "en": "Ezo / Ainu lands (schematic)",
        "from": 700,
        "to": 1869,
    },
    "JP-02": {"zh_hans": "陆奥国", "ja": "陸奥国", "en": "Mutsu", "from": 701, "to": 1868},
    "JP-03": {"zh_hans": "陆奥国", "ja": "陸奥国", "en": "Mutsu", "from": 701, "to": 1868},
    "JP-04": {"zh_hans": "陆奥国", "ja": "陸奥国", "en": "Mutsu", "from": 701, "to": 1868},
    "JP-05": {"zh_hans": "出羽国", "ja": "出羽国", "en": "Dewa", "from": 708, "to": 1868},
    "JP-06": {"zh_hans": "出羽国", "ja": "出羽国", "en": "Dewa", "from": 708, "to": 1868},
    "JP-07": {"zh_hans": "陆奥国（岩代・磐城）", "ja": "陸奥国（岩代・磐城）", "en": "Mutsu (Iwashiro/Iwaki)", "from": 701, "to": 1868},
    "JP-08": {"zh_hans": "常陆国", "ja": "常陸国", "en": "Hitachi", "from": 701, "to": 1868},
    "JP-09": {"zh_hans": "下野国", "ja": "下野国", "en": "Shimotsuke", "from": 701, "to": 1868},
    "JP-10": {"zh_hans": "上野国", "ja": "上野国", "en": "Kōzuke", "from": 701, "to": 1868},
    "JP-11": {"zh_hans": "武藏国", "ja": "武蔵国", "en": "Musashi", "from": 701, "to": 1868},
    "JP-12": {"zh_hans": "下总・上总・安房", "ja": "下総・上総・安房", "en": "Shimōsa / Kazusa / Awa", "from": 701, "to": 1868},
    "JP-13": {"zh_hans": "武藏国", "ja": "武蔵国", "en": "Musashi", "from": 701, "to": 1868},
    "JP-14": {"zh_hans": "相模国", "ja": "相模国", "en": "Sagami", "from": 701, "to": 1868},
    "JP-15": {"zh_hans": "越后国・佐渡国", "ja": "越後国・佐渡国", "en": "Echigo / Sado", "from": 701, "to": 1868},
    "JP-16": {"zh_hans": "越中国", "ja": "越中国", "en": "Etchū", "from": 701, "to": 1868},
    "JP-17": {"zh_hans": "加贺国・能登国", "ja": "加賀国・能登国", "en": "Kaga / Noto", "from": 823, "to": 1868},
    "JP-18": {"zh_hans": "越前国", "ja": "越前国", "en": "Echizen", "from": 701, "to": 1868},
    "JP-19": {"zh_hans": "甲斐国", "ja": "甲斐国", "en": "Kai", "from": 701, "to": 1868},
    "JP-20": {"zh_hans": "信浓国", "ja": "信濃国", "en": "Shinano", "from": 701, "to": 1868},
    "JP-21": {"zh_hans": "美浓国・飞驒国", "ja": "美濃国・飛騨国", "en": "Mino / Hida", "from": 701, "to": 1868},
    "JP-22": {"zh_hans": "骏河・远江・伊豆", "ja": "駿河・遠江・伊豆", "en": "Suruga / Tōtōmi / Izu", "from": 701, "to": 1868},
    "JP-23": {"zh_hans": "尾张国・三河国", "ja": "尾張国・三河国", "en": "Owari / Mikawa", "from": 701, "to": 1868},
    "JP-24": {"zh_hans": "伊势・伊贺・志摩", "ja": "伊勢・伊賀・志摩", "en": "Ise / Iga / Shima", "from": 701, "to": 1868},
    "JP-25": {"zh_hans": "近江国", "ja": "近江国", "en": "Ōmi", "from": 701, "to": 1868},
    "JP-26": {"zh_hans": "山城国", "ja": "山城国", "en": "Yamashiro", "from": 701, "to": 1868},
    "JP-27": {"zh_hans": "摄津国", "ja": "摂津国", "en": "Settsu", "from": 701, "to": 1868},
    "JP-28": {"zh_hans": "播磨・但马・丹波等", "ja": "播磨・但馬・丹波等", "en": "Harima / Tajima / Tanba…", "from": 701, "to": 1868},
    "JP-29": {"zh_hans": "大和国", "ja": "大和国", "en": "Yamato", "from": 701, "to": 1868},
    "JP-30": {"zh_hans": "纪伊国", "ja": "紀伊国", "en": "Kii", "from": 701, "to": 1868},
    "JP-31": {"zh_hans": "因幡国・伯耆国", "ja": "因幡国・伯耆国", "en": "Inaba / Hōki", "from": 701, "to": 1868},
    "JP-32": {"zh_hans": "出云・石见・隐岐", "ja": "出雲・石見・隠岐", "en": "Izumo / Iwami / Oki", "from": 701, "to": 1868},
    "JP-33": {"zh_hans": "备前・备中・美作", "ja": "備前・備中・美作", "en": "Bizen / Bitchū / Mimasaka", "from": 701, "to": 1868},
    "JP-34": {"zh_hans": "安艺国・备后国", "ja": "安芸国・備後国", "en": "Aki / Bingo", "from": 701, "to": 1868},
    "JP-35": {"zh_hans": "周防国・长门国", "ja": "周防国・長門国", "en": "Suo / Nagato", "from": 701, "to": 1868},
    "JP-36": {"zh_hans": "阿波国", "ja": "阿波国", "en": "Awa", "from": 701, "to": 1868},
    "JP-37": {"zh_hans": "赞岐国", "ja": "讃岐国", "en": "Sanuki", "from": 701, "to": 1868},
    "JP-38": {"zh_hans": "伊予国", "ja": "伊予国", "en": "Iyo", "from": 701, "to": 1868},
    "JP-39": {"zh_hans": "土佐国", "ja": "土佐国", "en": "Tosa", "from": 701, "to": 1868},
    "JP-40": {"zh_hans": "筑前国・筑后国", "ja": "筑前国・筑後国", "en": "Chikuzen / Chikugo", "from": 701, "to": 1868},
    "JP-41": {"zh_hans": "肥前国", "ja": "肥前国", "en": "Hizen", "from": 701, "to": 1868},
    "JP-42": {"zh_hans": "肥前国（含壹岐・对马）", "ja": "肥前国（含壱岐・対馬）", "en": "Hizen (w/ Iki·Tsushima)", "from": 701, "to": 1868},
    "JP-43": {"zh_hans": "肥后国", "ja": "肥後国", "en": "Higo", "from": 701, "to": 1868},
    "JP-44": {"zh_hans": "丰后国", "ja": "豊後国", "en": "Bungo", "from": 701, "to": 1868},
    "JP-45": {"zh_hans": "日向国", "ja": "日向国", "en": "Hyūga", "from": 701, "to": 1868},
    "JP-46": {"zh_hans": "萨摩国・大隅国", "ja": "薩摩国・大隅国", "en": "Satsuma / Ōsumi", "from": 701, "to": 1868},
    "JP-47": {
        "zh_hans": "琉球（国／按司联立示意）",
        "ja": "琉球（国・按司聯立示意）",
        "en": "Ryukyu (schematic)",
        "from": 1187,
        "to": 1879,
    },
}

# Optional early-modern / meiji rename overlays (non-overlapping primary track additions)
SPECIAL: dict[str, list[dict]] = {
    "JP-13": [
        {
            "from_year": 1603,
            "to_year": 1868,
            "kind": "domain",
            "names": {
                "zh_hans": "江户（幕府所在）",
                "ja": "江戸（幕府所在）",
                "en": "Edo (shogunal seat)",
            },
        },
        {
            "from_year": 1868,
            "to_year": 1943,
            "kind": "prefecture",
            "names": {"zh_hans": "东京府", "ja": "東京府", "en": "Tokyo-fu"},
        },
        {
            "from_year": 1943,
            "to_year": 2026,
            "kind": "prefecture",
            "names": {"zh_hans": "东京都", "ja": "東京都", "en": "Tokyo-to"},
        },
    ],
    "JP-01": [
        {
            "from_year": 1603,
            "to_year": 1869,
            "kind": "domain",
            "names": {
                "zh_hans": "松前藩／虾夷地（示意）",
                "ja": "松前藩・蝦夷地（示意）",
                "en": "Matsumae / Ezo (schematic)",
            },
        },
        {
            "from_year": 1869,
            "to_year": 1886,
            "kind": "prefecture",
            "names": {
                "zh_hans": "开拓使／三县（过渡）",
                "ja": "開拓使・三県（過渡）",
                "en": "Kaitakushi / 3 prefs",
            },
        },
        {
            "from_year": 1886,
            "to_year": 2026,
            "kind": "prefecture",
            "names": {"zh_hans": "北海道", "ja": "北海道", "en": "Hokkaido"},
        },
    ],
    "JP-47": [
        {
            "from_year": 1872,
            "to_year": 1879,
            "kind": "domain",
            "names": {"zh_hans": "琉球藩", "ja": "琉球藩", "en": "Ryukyu Domain"},
        },
        {
            "from_year": 1879,
            "to_year": 2026,
            "kind": "prefecture",
            "names": {"zh_hans": "冲绳县", "ja": "沖縄県", "en": "Okinawa"},
        },
    ],
    "JP-26": [
        {
            "from_year": 794,
            "to_year": 1868,
            "kind": "province",
            "names": {
                "zh_hans": "山城国（平安京所在）",
                "ja": "山城国（平安京所在）",
                "en": "Yamashiro (Heian-kyō)",
            },
        },
        {
            "from_year": 1868,
            "to_year": 2026,
            "kind": "prefecture",
            "names": {"zh_hans": "京都府", "ja": "京都府", "en": "Kyoto-fu"},
        },
    ],
    "JP-27": [
        {
            "from_year": 1868,
            "to_year": 2026,
            "kind": "prefecture",
            "names": {"zh_hans": "大阪府", "ja": "大阪府", "en": "Osaka-fu"},
        },
    ],
}


def n(zh, ja, en):
    return {"zh_hans": zh, "ja": ja, "en": en}


def span(from_year, to_year, kind, names, note=None):
    s = {
        "from_year": int(from_year),
        "to_year": int(to_year),
        "kind": kind,
        "names": names,
    }
    if note:
        s["note"] = note
    return s


def archaeology_spans():
    return [
        span(
            -14000,
            -400,
            "archaeology",
            n("绳文文化分布（示意）", "縄文文化分布（示意）", "Jōmon (schematic)"),
            "考古阶段示意，非政区名",
        ),
        span(
            -400,
            250,
            "archaeology",
            n("弥生文化圈（示意）", "弥生文化圏（示意）", "Yayoi (schematic)"),
        ),
        span(
            250,
            701,
            "archaeology",
            n("古坟时代地域社会（示意）", "古墳時代の地域社会（示意）", "Kofun-era local societies"),
        ),
    ]


def load_prefs():
    path = ROOT / "web" / "data" / "japan_prefectures.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for f in data["features"]:
        p = f["properties"]
        out[p["code"]] = {
            "code": p["code"],
            "names": {
                "zh_hans": p["name_zh"],
                "ja": p["name_ja"],
                "en": p["name_en"],
            },
        }
    return out


def build_spans_for(code: str, modern: dict) -> list[dict]:
    spans = archaeology_spans()
    special = SPECIAL.get(code)

    if special:
        # Drop generic province/domain/prefecture if SPECIAL provides full modern track;
        # still insert 令制国 before first special if needed.
        prov = PROVINCES.get(code)
        first_special_from = min(s["from_year"] for s in special)
        if prov and prov["from"] < first_special_from:
            spans.append(
                span(
                    prov["from"],
                    min(prov["to"], first_special_from),
                    "province",
                    n(prov["zh_hans"], prov["ja"], prov["en"]),
                    "令制国骨架（示意）",
                )
            )
        # Optional domain band before meiji when not covered
        if code not in ("JP-13", "JP-01", "JP-47") and first_special_from > 1603:
            spans.append(
                span(
                    1603,
                    first_special_from,
                    "domain",
                    n("幕藩领（示意）", "幕藩領（示意）", "Bakuhan domains (schematic)"),
                )
            )
        spans.extend(special)
        return merge_touching(spans)

    prov = PROVINCES[code]
    spans.append(
        span(
            prov["from"],
            1603,
            "province",
            n(prov["zh_hans"], prov["ja"], prov["en"]),
            "令制国骨架（示意）",
        )
    )
    spans.append(
        span(
            1603,
            1871,
            "domain",
            n(
                f"幕藩领 · {prov['zh_hans']}域（示意）",
                f"幕藩領・{prov['ja']}域（示意）",
                f"Bakuhan · {prov['en']} (schematic)",
            ),
        )
    )
    spans.append(
        span(
            1871,
            2026,
            "prefecture",
            modern["names"],
            "废藩置县以后的近代县名（示意；合并改名从略）",
        )
    )
    return merge_touching(spans)


def merge_touching(spans: list[dict]) -> list[dict]:
    """Sort and clip obvious inversions; keep overlaps as separate stacked rows."""
    spans = sorted(spans, key=lambda s: (s["from_year"], s["to_year"], s["kind"]))
    cleaned = []
    for s in spans:
        if s["to_year"] <= s["from_year"]:
            continue
        cleaned.append(s)
    return cleaned


def main():
    prefs = load_prefs()
    prefectures = {}
    for code, modern in sorted(prefs.items()):
        prefectures[code] = {
            **modern,
            "spans": build_spans_for(code, modern),
        }

    doc = {
        "meta": {
            "version": "0.1.0",
            "year_min": -14000,
            "year_max": 2026,
            "note": "现代都道府县范围内的地名／政区沿革示意索引；考古与令制国为示意标签，非精确边界。对齐日文维基大框架。",
        },
        "kinds": {
            "archaeology": {"zh_hans": "考古", "ja": "考古", "en": "Archaeology"},
            "province": {"zh_hans": "令制国", "ja": "令制国", "en": "Province"},
            "domain": {"zh_hans": "藩领", "ja": "藩領", "en": "Domain"},
            "prefecture": {"zh_hans": "近代县", "ja": "近代県", "en": "Prefecture"},
        },
        "prefectures": prefectures,
    }
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    OUT.write_text(text + "\n", encoding="utf-8")
    WEB_OUT.parent.mkdir(parents=True, exist_ok=True)
    WEB_OUT.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"wrote {WEB_OUT}")
    print(f"prefectures={len(prefectures)}")


if __name__ == "__main__":
    main()
