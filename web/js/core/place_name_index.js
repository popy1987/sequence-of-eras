/**
 * Geographic × time name index for modern prefectures (schematic spans).
 */
import { pickName } from "./names.js";

const DATA_URL = new URL("../../data/prefecture_name_spans.json", import.meta.url).href;

const KIND_COLOR = {
  archaeology: "#8b7355",
  province: "#2f5d8c",
  domain: "#6b4e71",
  prefecture: "#b33a2b",
};

let cache = null;

export async function loadPlaceNameIndex() {
  if (cache) return cache;
  const res = await fetch(DATA_URL);
  if (!res.ok) throw new Error(`place name index HTTP ${res.status}`);
  cache = await res.json();
  return cache;
}

export function kindColor(kind) {
  return KIND_COLOR[kind] || "#5b7c6a";
}

export function getPrefectureEntry(index, code) {
  if (!index || !code) return null;
  return index.prefectures?.[code] || null;
}

/** Shared axis range for proportional bars (index meta, fallback from spans). */
export function axisRange(index, entry) {
  const spans = entry?.spans || [];
  let y0 = index?.meta?.year_min ?? -14000;
  let y1 = index?.meta?.year_max ?? 2026;
  if (spans.length) {
    y0 = Math.min(y0, ...spans.map((s) => s.from_year));
    y1 = Math.max(y1, ...spans.map((s) => s.to_year));
  }
  if (y1 <= y0) y1 = y0 + 1;
  return { yearMin: y0, yearMax: y1, span: y1 - y0 };
}

export function spanStyle(span, range) {
  const left = ((span.from_year - range.yearMin) / range.span) * 100;
  const width = ((span.to_year - span.from_year) / range.span) * 100;
  return {
    left: `${Math.max(0, left)}%`,
    width: `${Math.max(0.35, width)}%`,
    background: kindColor(span.kind),
  };
}

export function formatYearRange(from, to, formatYear) {
  if (from === to) return formatYear(from);
  return `${formatYear(from)} – ${formatYear(to)}`;
}

export function kindLabel(index, kind, locale) {
  const row = index?.kinds?.[kind];
  if (!row) return kind;
  return pickName(row, locale) || kind;
}
