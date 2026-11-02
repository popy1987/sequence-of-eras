/**
 * MapLibre GL JS engine — same MapFrame contract as svg_mercator.
 * Loads maplibre-gl from CDN on first use (no bundler required).
 * Optional GLB terrain underlay via Custom Layer + Three.js.
 */
import { MAP_ENGINE_EVENTS, MAP_SELECT_KIND } from "../contract.js";
import { pickName } from "../../core/names.js";
import { getLocale, t } from "../../i18n/index.js";
import {
  resolveTerrainEnabled,
  resolveTerrainCalibMode,
} from "../../config.js";
import {
  createTerrainGlbLayer,
  TERRAIN_LAYER_ID,
} from "./terrain_glb_layer.js";

const MAPLIBRE_JS = new URL("../../../vendor/maplibre-gl/maplibre-gl.js", import.meta.url).href;
const MAPLIBRE_CSS = new URL("../../../vendor/maplibre-gl/maplibre-gl.css", import.meta.url).href;
const PREFECTURES_URL = new URL("../../../data/japan_prefectures.json", import.meta.url).href;

/** Japan schematic home view (WGS84). */
const HOME_BOUNDS = [
  [122.5, 24.0],
  [146.0, 46.5],
];

const SRC = {
  coast: "soe-coast",
  polities: "soe-polities",
  markers: "soe-markers",
  disputes: "soe-disputes",
  prefectures: "soe-prefectures",
};

const LAYER = {
  coastFill: "soe-coast-fill",
  coastLine: "soe-coast-line",
  polityFill: "soe-polity-fill",
  polityLine: "soe-polity-line",
  markerCircle: "soe-marker-circle",
  markerLabel: "soe-marker-label",
  disputeCircle: "soe-dispute-circle",
  disputeLabel: "soe-dispute-label",
  prefectureLine: "soe-prefecture-line",
  prefectureLabel: "soe-prefecture-label",
};

let loadPromise = null;

function ensureCss() {
  if (document.querySelector(`link[data-soe-maplibre]`)) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = MAPLIBRE_CSS;
  link.dataset.soeMaplibre = "1";
  document.head.appendChild(link);
}

function loadMapLibre() {
  if (globalThis.maplibregl) return Promise.resolve(globalThis.maplibregl);
  if (loadPromise) return loadPromise;
  ensureCss();
  loadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = MAPLIBRE_JS;
    script.async = true;
    script.onload = () => {
      if (!globalThis.maplibregl) {
        reject(new Error("maplibre-gl loaded but global maplibregl missing"));
        return;
      }
      resolve(globalThis.maplibregl);
    };
    script.onerror = () =>
      reject(new Error(`Failed to load MapLibre from ${MAPLIBRE_JS}`));
    document.head.appendChild(script);
  });
  return loadPromise;
}

function emptyFc() {
  return { type: "FeatureCollection", features: [] };
}

function polityCollection(polities) {
  return {
    type: "FeatureCollection",
    features: (polities || [])
      .filter((p) => p && p.geometry)
      .map((p) => ({
        type: "Feature",
        id: p.id,
        properties: {
          id: p.id,
          color: p.color || "#4a6741",
          mode: p.mode || "direct",
        },
        geometry: p.geometry,
      })),
  };
}

function markerCollection(markers, locale) {
  return {
    type: "FeatureCollection",
    features: (markers || [])
      .filter((m) => m && m.lon != null && m.lat != null)
      .map((m, i) => ({
        type: "Feature",
        id: i,
        properties: {
          id: m.id,
          kind: m.kind || "site",
          label: pickName(m.names, locale) || m.id,
          conflict: m.conflict_class || "",
          payload: JSON.stringify(m),
        },
        geometry: { type: "Point", coordinates: [m.lon, m.lat] },
      })),
  };
}

function disputeCollection(disputes, locale) {
  return {
    type: "FeatureCollection",
    features: (disputes || [])
      .filter((d) => d && d.geometry && d.geometry.lon != null && d.geometry.lat != null)
      .map((d, i) => ({
        type: "Feature",
        id: i,
        properties: {
          id: d.id,
          label: pickName(d.names, locale) || d.id,
          payload: JSON.stringify(d),
        },
        geometry: {
          type: "Point",
          coordinates: [d.geometry.lon, d.geometry.lat],
        },
      })),
  };
}

function baseStyle() {
  return {
    version: 8,
    name: "soe-schematic",
    // Demo glyphs for symbol labels; coastline/polities do not need tiles.
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {},
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": "#9bb7c9" },
      },
    ],
  };
}

/**
 * @param {HTMLElement} host
 * @param {object} [options]
 */
export function createMapLibreEngine(host, options = {}) {
  const listeners = { [MAP_ENGINE_EVENTS.SELECT]: [] };
  let map = null;
  let pendingFrame = null;
  let destroyed = false;
  let terrainLayer = null;
  let terrainReady = false;
  const polityById = new Map();
  const terrainEnabled =
    options.terrain !== undefined
      ? !!options.terrain
      : resolveTerrainEnabled();
  const calibMode =
    options.terrainCalib !== undefined
      ? !!options.terrainCalib
      : resolveTerrainCalibMode();

  host.innerHTML = "";
  const container = document.createElement("div");
  container.className = "soe-maplibre-host";
  container.setAttribute("role", "img");
  container.setAttribute(
    "aria-label",
    options.ariaLabel || "可拖动缩放的日本历史地图"
  );
  host.appendChild(container);

  // Overlay on host (not map container) — MapLibre owns container children.
  const progressEl = document.createElement("div");
  progressEl.className = "soe-terrain-progress";
  progressEl.hidden = true;
  progressEl.innerHTML =
    '<div class="soe-terrain-progress__label">Terrain 0%</div>' +
    '<div class="soe-terrain-progress__track">' +
    '<div class="soe-terrain-progress__bar" style="width:0%"></div>' +
    "</div>";
  host.appendChild(progressEl);

  let prefecturesVisible = true;
  const prefectureButton = document.createElement("button");
  prefectureButton.type = "button";
  prefectureButton.className = "ghost-btn soe-prefecture-toggle";
  prefectureButton.textContent = t("map.prefectures");
  prefectureButton.setAttribute("aria-pressed", "true");
  prefectureButton.addEventListener("click", () => {
    prefecturesVisible = !prefecturesVisible;
    prefectureButton.setAttribute("aria-pressed", String(prefecturesVisible));
    setPrefectureVisibility();
  });
  host.appendChild(prefectureButton);

  function setProgress(pct, label) {
    progressEl.hidden = false;
    const bar = progressEl.querySelector(".soe-terrain-progress__bar");
    const text = progressEl.querySelector(".soe-terrain-progress__label");
    if (bar) bar.style.width = `${pct}%`;
    if (text) text.textContent = label || `Terrain ${pct}%`;
  }

  function hideProgress() {
    progressEl.hidden = true;
  }

  function setCoastTerrainMode(active) {
    if (!map || !map.getLayer(LAYER.coastFill)) return;
    if (active) {
      map.setPaintProperty(LAYER.coastFill, "fill-opacity", 0);
      map.setPaintProperty(LAYER.coastLine, "line-opacity", 0.18);
      map.setPaintProperty(LAYER.coastLine, "line-width", 0.6);
    } else {
      map.setPaintProperty(LAYER.coastFill, "fill-opacity", 0.95);
      map.setPaintProperty(LAYER.coastLine, "line-opacity", 1);
      map.setPaintProperty(LAYER.coastLine, "line-width", 1.1);
    }
  }

  function emit(type, payload) {
    (listeners[type] || []).forEach((fn) => fn(payload));
  }

  function ensureSources() {
    if (!map.getSource(SRC.coast)) {
      map.addSource(SRC.coast, { type: "geojson", data: emptyFc() });
      map.addLayer({
        id: LAYER.coastFill,
        type: "fill",
        source: SRC.coast,
        paint: {
          "fill-color": "#e7eef3",
          "fill-opacity": 0.95,
        },
      });
      map.addLayer({
        id: LAYER.coastLine,
        type: "line",
        source: SRC.coast,
        paint: {
          "line-color": "#5f7388",
          "line-width": 1.1,
        },
      });
    }
    if (!map.getSource(SRC.polities)) {
      map.addSource(SRC.polities, { type: "geojson", data: emptyFc() });
      map.addLayer({
        id: LAYER.polityFill,
        type: "fill",
        source: SRC.polities,
        paint: {
          "fill-color": ["get", "color"],
          "fill-opacity": 0.55,
        },
      });
      map.addLayer({
        id: LAYER.polityLine,
        type: "line",
        source: SRC.polities,
        paint: {
          "line-color": ["get", "color"],
          "line-width": 1.4,
          "line-opacity": 0.9,
        },
      });
    }
    if (!map.getSource(SRC.markers)) {
      map.addSource(SRC.markers, { type: "geojson", data: emptyFc() });
      map.addLayer({
        id: LAYER.markerCircle,
        type: "circle",
        source: SRC.markers,
        paint: {
          "circle-radius": [
            "match",
            ["get", "kind"],
            "capital",
            7,
            "kofun",
            5,
            "event",
            5,
            5,
          ],
          "circle-color": [
            "match",
            ["get", "kind"],
            "capital",
            "#b33a2b",
            "kofun",
            "#8b5a2b",
            "event",
            "#a33b2b",
            "castle",
            "#6b4e71",
            "#5b7c6a",
          ],
          "circle-stroke-width": 1.2,
          "circle-stroke-color": "#f4f9fc",
        },
      });
      map.addLayer({
        id: LAYER.markerLabel,
        type: "symbol",
        source: SRC.markers,
        layout: {
          "text-field": ["get", "label"],
          "text-size": 11,
          "text-offset": [0, 1.15],
          "text-anchor": "top",
          "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
          "text-optional": true,
        },
        paint: {
          "text-color": "#152238",
          "text-halo-color": "rgba(244,249,252,0.92)",
          "text-halo-width": 1.4,
        },
      });
    }
    if (!map.getSource(SRC.disputes)) {
      map.addSource(SRC.disputes, { type: "geojson", data: emptyFc() });
      map.addLayer({
        id: LAYER.disputeCircle,
        type: "circle",
        source: SRC.disputes,
        paint: {
          "circle-radius": 9,
          "circle-color": "rgba(179,58,43,0.2)",
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#b33a2b",
        },
      });
      map.addLayer({
        id: LAYER.disputeLabel,
        type: "symbol",
        source: SRC.disputes,
        layout: {
          "text-field": "争",
          "text-size": 11,
          "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
        },
        paint: {
          "text-color": "#b33a2b",
          "text-halo-color": "#f4f9fc",
          "text-halo-width": 1.2,
        },
      });
    }
  }

  function prefectureLabelName(locale) {
    const key = locale === "ja" ? "name_ja" : locale === "en" ? "name_en" : "name_zh";
    return ["coalesce", ["get", key], ["get", "name_ja"], ["get", "name_en"]];
  }

  function updatePrefectureLocale(locale) {
    prefectureButton.textContent = t("map.prefectures");
    if (map.getLayer(LAYER.prefectureLabel)) {
      map.setLayoutProperty(
        LAYER.prefectureLabel,
        "text-field",
        prefectureLabelName(locale)
      );
    }
  }

  function setPrefectureVisibility() {
    if (!map) return;
    const visibility = prefecturesVisible ? "visible" : "none";
    [LAYER.prefectureLine, LAYER.prefectureLabel].forEach((id) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visibility);
    });
  }

  async function loadPrefectures() {
    try {
      const res = await fetch(PREFECTURES_URL);
      if (!res.ok) throw new Error(`prefectures HTTP ${res.status}`);
      const data = await res.json();
      if (destroyed || !map || map.getSource(SRC.prefectures)) return;
      map.addSource(SRC.prefectures, {
        type: "geojson",
        data,
        attribution: "© geoBoundaries (ODbL 1.0)",
      });
      map.addLayer(
        {
          id: LAYER.prefectureLine,
          type: "line",
          source: SRC.prefectures,
          paint: {
            "line-color": "#152238",
            "line-width": 0.9,
            "line-opacity": 0.72,
          },
        },
        LAYER.markerCircle
      );
      map.addLayer(
        {
          id: LAYER.prefectureLabel,
          type: "symbol",
          source: SRC.prefectures,
          layout: {
            "text-field": prefectureLabelName(getLocale()),
            "text-size": 11,
            "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
            "text-optional": true,
          },
          paint: {
            "text-color": "#152238",
            "text-halo-color": "rgba(244,249,252,0.95)",
            "text-halo-width": 1.4,
          },
        },
        LAYER.markerCircle
      );
      setPrefectureVisibility();
    } catch (err) {
      prefectureButton.hidden = true;
      console.error("[prefectures]", err);
    }
  }

  function applyFrame(frame) {
    if (!map || !frame) return;
    const locale = frame.locale || getLocale();
    ensureSources();

    polityById.clear();
    (frame.polities || []).forEach((p) => polityById.set(p.id, p));

    const coast = frame.coastline
      ? {
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              properties: {},
              geometry: frame.coastline,
            },
          ],
        }
      : emptyFc();

    map.getSource(SRC.coast).setData(coast);
    map.getSource(SRC.polities).setData(polityCollection(frame.polities));
    map.getSource(SRC.markers).setData(markerCollection(frame.markers, locale));
    map.getSource(SRC.disputes).setData(disputeCollection(frame.disputes, locale));
    updatePrefectureLocale(locale);
  }

  function fitHome() {
    if (!map) return;
    map.fitBounds(HOME_BOUNDS, { padding: 48, duration: 0 });
  }

  function bindClicks() {
    map.on("click", LAYER.polityFill, (e) => {
      const f = e.features && e.features[0];
      if (!f) return;
      const data = polityById.get(f.properties.id);
      if (data) {
        emit(MAP_ENGINE_EVENTS.SELECT, {
          kind: MAP_SELECT_KIND.POLITY,
          data,
        });
      }
    });
    map.on("click", LAYER.markerCircle, (e) => {
      const f = e.features && e.features[0];
      if (!f) return;
      try {
        const data = JSON.parse(f.properties.payload);
        emit(MAP_ENGINE_EVENTS.SELECT, {
          kind: MAP_SELECT_KIND.MARKER,
          data,
        });
      } catch (_) {
        /* ignore */
      }
    });
    map.on("click", LAYER.markerLabel, (e) => {
      const f = e.features && e.features[0];
      if (!f) return;
      try {
        const data = JSON.parse(f.properties.payload);
        emit(MAP_ENGINE_EVENTS.SELECT, {
          kind: MAP_SELECT_KIND.MARKER,
          data,
        });
      } catch (_) {
        /* ignore */
      }
    });
    map.on("click", LAYER.disputeCircle, (e) => {
      const f = e.features && e.features[0];
      if (!f) return;
      try {
        const data = JSON.parse(f.properties.payload);
        emit(MAP_ENGINE_EVENTS.SELECT, {
          kind: MAP_SELECT_KIND.DISPUTE,
          data,
        });
      } catch (_) {
        /* ignore */
      }
    });

    const hover = [
      LAYER.polityFill,
      LAYER.markerCircle,
      LAYER.markerLabel,
      LAYER.disputeCircle,
    ];
    hover.forEach((id) => {
      map.on("mouseenter", id, () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", id, () => {
        map.getCanvas().style.cursor = "";
      });
    });
  }

  const ready = loadMapLibre()
    .then((maplibregl) => {
      if (destroyed) return;
      map = new maplibregl.Map({
        container,
        style: baseStyle(),
        attributionControl: false,
        fadeDuration: 0,
      });
      map.addControl(
        new maplibregl.NavigationControl({ showCompass: false }),
        "top-right"
      );
      map.addControl(
        new maplibregl.AttributionControl({ compact: true }),
        "bottom-right"
      );

      return new Promise((resolve) => {
        map.on("load", () => {
          if (destroyed) return;
          ensureSources();
          loadPrefectures();
          bindClicks();
          fitHome();

          if (terrainEnabled) {
            setProgress(0, "Terrain…");
            terrainLayer = createTerrainGlbLayer({
              maplibregl,
              calibMode,
              onProgress: ({ pct }) => setProgress(pct),
              onReady: (info) => {
                if (destroyed) return;
                terrainReady = true;
                setCoastTerrainMode(true);
                hideProgress();
                console.info(
                  `[terrain] ready mode=${info.mode}`,
                  info.aabb
                );
              },
              onError: (err) => {
                hideProgress();
                setCoastTerrainMode(false);
                console.error("[terrain]", err);
                const tip = document.createElement("p");
                tip.className = "soe-terrain-fallback";
                tip.textContent = `Terrain failed: ${err.message}`;
                host.appendChild(tip);
                setTimeout(() => tip.remove(), 6000);
              },
            });
            // Under coast / polity / markers so GeoJSON stays interactive on top.
            map.addLayer(terrainLayer, LAYER.coastFill);
          }

          if (pendingFrame) {
            applyFrame(pendingFrame);
            pendingFrame = null;
          }
          resolve();
        });
      });
    })
    .catch((err) => {
      console.error(err);
      container.innerHTML = `<p class="soe-maplibre-error">${err.message}</p>`;
      throw err;
    });

  return {
    id: "maplibre",
    ready,
    terrainEnabled,
    isTerrainReady: () => terrainReady,
    getTerrainCalib() {
      return terrainLayer?.getCalib?.() ?? null;
    },
    dumpTerrainCalib() {
      return terrainLayer?.dumpTerrainCalib?.() ?? null;
    },
    getTerrainAffine() {
      return terrainLayer?.getAffineInfo?.() ?? null;
    },
    setFrame(frame) {
      if (!map || !map.isStyleLoaded()) {
        pendingFrame = frame;
        return;
      }
      applyFrame(frame);
      if (terrainReady) setCoastTerrainMode(true);
    },
    fitHome,
    on(type, fn) {
      (listeners[type] || (listeners[type] = [])).push(fn);
    },
    destroy() {
      destroyed = true;
      if (map) {
        if (terrainLayer && map.getLayer(TERRAIN_LAYER_ID)) {
          try {
            map.removeLayer(TERRAIN_LAYER_ID);
          } catch (_) {
            /* ignore */
          }
        }
        map.remove();
        map = null;
      }
      terrainLayer = null;
      host.innerHTML = "";
    },
  };
}
