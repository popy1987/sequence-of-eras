/** Runtime switches. Change MAP_ENGINE to swap implementations without touching app logic. */
export const MAP_ENGINE = "svg_mercator";

/**
 * Allow URL override for local comparison:
 *   ?engine=svg_mercator
 *   ?engine=maplibre
 */
export function resolveMapEngineId() {
  const q = new URLSearchParams(location.search).get("engine");
  return q || MAP_ENGINE;
}
