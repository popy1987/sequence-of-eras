/** Atlas queries independent of any map engine. */

import { ordinal } from "./chrono.js";
import { pickName } from "./names.js";
import { getLocale, t } from "../i18n/index.js";

export { pickName };

function covering(list, ord, fromKey = "query_from", toKey = "query_to") {
  return (list || []).filter((item) => {
    const a = item[fromKey];
    const b = item[toKey] == null ? Number.POSITIVE_INFINITY : item[toKey];
    return a <= ord && ord <= b;
  });
}

export function phaseForYear(atlas, year) {
  let hit = null;
  for (const p of atlas.phases) {
    if (year >= p.from_year && year <= p.to_year) hit = p;
  }
  return hit || atlas.phases[atlas.phases.length - 1];
}

export function periodLabel(atlas, year, locale = getLocale()) {
  const ord = ordinal(year, 7, 1);
  const hits = covering(
    atlas.periods.filter((p) => !p.region_id),
    ord
  );
  const best = hits.sort((a, b) => a.sort_order - b.sort_order).slice(-1)[0];
  return best ? pickName(best.names, locale) : "—";
}

export function activeDisputes(atlas, year) {
  const ord = ordinal(year, 7, 1);
  return covering(atlas.disputes, ord).filter((d) => d.status === "active");
}

/**
 * Events valid on this year. Default: importance 1–3, or timeline_policy=always.
 * Pass { all: true } to include importance 4–5.
 */
export function activeEvents(atlas, year, { all = false } = {}) {
  const list = atlas.events || [];
  return list.filter((ev) => {
    if (year < ev.from_year || year > ev.to_year) return false;
    if (all) return true;
    if (ev.timeline_policy === "always") return true;
    return (ev.importance || 5) <= 3;
  });
}

function eventMarkers(atlas, year) {
  return activeEvents(atlas, year).map((ev) => ({
    id: ev.id,
    lon: ev.lon,
    lat: ev.lat,
    names: ev.names,
    kind: "event",
    event_kind: ev.kind,
    conflict_class: ev.conflict_class || null,
    from_year: ev.from_year,
    to_year: ev.to_year,
    importance: ev.importance,
    short_note: ev.short_note,
    alignment: ev.alignment,
  })).filter((m) => m.lon != null && m.lat != null);
}

/** Build the engine-agnostic render frame for a year. */
export function buildMapFrame(atlas, year, locale = getLocale()) {
  const phase = phaseForYear(atlas, year);
  const markers = [...(phase.markers || []), ...eventMarkers(atlas, year)];
  return {
    year,
    locale,
    coastline: atlas.coastline,
    polities: phase.polities || [],
    markers,
    disputes: activeDisputes(atlas, year),
    events: activeEvents(atlas, year),
    phase,
  };
}

export async function loadAtlas(url = "data/atlas.json") {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(t("error.atlasMissing"));
  }
  return res.json();
}
