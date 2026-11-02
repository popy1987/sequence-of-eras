/** Runtime switches. Change MAP_ENGINE to swap implementations without touching app logic. */
export const MAP_ENGINE = "maplibre";

/**
 * Allow URL override for local comparison:
 *   ?engine=maplibre
 *   ?engine=svg_mercator
 */
export function resolveMapEngineId() {
  const q = new URLSearchParams(location.search).get("engine");
  return q || MAP_ENGINE;
}
