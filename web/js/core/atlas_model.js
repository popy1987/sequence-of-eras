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

/** Build the engine-agnostic render frame for a year. */
export function buildMapFrame(atlas, year, locale = getLocale()) {
  const phase = phaseForYear(atlas, year);
  return {
    year,
    locale,
    coastline: atlas.coastline,
    polities: phase.polities || [],
    markers: phase.markers || [],
    disputes: activeDisputes(atlas, year),
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
