/** Runtime switches. Change MAP_ENGINE to swap implementations without touching app logic. */
export const MAP_ENGINE = "maplibre";

/** GLB terrain underlay for maplibre (Custom Layer + Three). */
export const TERRAIN_GLB = true;

/**
 * Allow URL override for local comparison:
 *   ?engine=maplibre
 *   ?engine=svg_mercator
 */
export function resolveMapEngineId() {
  const q = new URLSearchParams(location.search).get("engine");
  return q || MAP_ENGINE;
}

/** ?terrain=0 disables GLB underlay; ?terrain=1 forces on. */
export function resolveTerrainEnabled() {
  const q = new URLSearchParams(location.search).get("terrain");
  if (q === "0" || q === "false") return false;
  if (q === "1" || q === "true") return true;
  return TERRAIN_GLB;
}

/** ?terrain_calib=1 enables raycast sampling for Japan_3D_Map.calib.json */
export function resolveTerrainCalibMode() {
  return new URLSearchParams(location.search).get("terrain_calib") === "1";
}
