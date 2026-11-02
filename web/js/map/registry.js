import { createSvgMercatorEngine } from "./engines/svg_mercator.js";
import { createMapLibreEngine } from "./engines/maplibre.js";

const factories = {
  svg_mercator: createSvgMercatorEngine,
  maplibre: createMapLibreEngine,
  // Future:
  // leaflet: createLeafletEngine,
};

export function listMapEngines() {
  return Object.keys(factories);
}

/**
 * @param {string} id
 * @param {HTMLElement} host
 * @param {object} [options]
 */
export function createMapEngine(id, host, options = {}) {
  const factory = factories[id];
  if (!factory) {
    throw new Error(
      `未知地图引擎 "${id}"。已注册：${listMapEngines().join(", ")}。见 doc/前端架构.md`
    );
  }
  return factory(host, options);
}
