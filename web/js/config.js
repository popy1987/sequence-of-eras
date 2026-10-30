/** Runtime switches. Change MAP_ENGINE to swap implementations without touching app logic. */
export const MAP_ENGINE = "svg_mercator";

/** Allow `?engine=svg_mercator` override for local comparison. */
export function resolveMapEngineId() {
  const q = new URLSearchParams(location.search).get("engine");
  return q || MAP_ENGINE;
}
