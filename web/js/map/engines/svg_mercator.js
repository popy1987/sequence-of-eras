/**
 * Default map engine: custom SVG + Mercator.
 * Implements the MapEngine contract in ../contract.js
 */
import { MAP_ENGINE_EVENTS, MAP_SELECT_KIND } from "../contract.js";
import { pickName } from "../../core/names.js";
import { getLocale } from "../../i18n/index.js";

function project(lon, lat) {
  const x = lon;
  const latRad = (lat * Math.PI) / 180;
  const y = Math.log(Math.tan(Math.PI / 4 + latRad / 2)) * (180 / Math.PI);
  return [x, -y];
}

function ringToPath(ring) {
  if (!ring || !ring.length) return "";
  if (Array.isArray(ring[0]) && Array.isArray(ring[0][0])) {
    return ring.map(ringToPath).join(" ");
  }
  return (
    ring
      .map((pt, i) => {
        if (!pt || pt.length < 2) return "";
        const lon = Number(pt[0]);
        const lat = Number(pt[1]);
        if (!Number.isFinite(lon) || !Number.isFinite(lat)) return "";
        const [x, y] = project(lon, lat);
        return `${i === 0 ? "M" : "L"}${x.toFixed(3)} ${y.toFixed(3)}`;
      })
      .filter(Boolean)
      .join(" ") + " Z"
  );
}

function geomToPath(geom) {
  if (!geom) return "";
  if (geom.type === "Polygon") {
    return (geom.coordinates || []).map(ringToPath).join(" ");
  }
  if (geom.type === "MultiPolygon") {
    return (geom.coordinates || [])
      .map((poly) => (poly || []).map(ringToPath).join(" "))
      .join(" ");
  }
  return "";
}

const SVG_NS = "http://www.w3.org/2000/svg";

function el(name, attrs = {}) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) {
    if (v != null) node.setAttribute(k, String(v));
  }
  return node;
}

function clearGroup(g) {
  while (g.firstChild) g.removeChild(g.firstChild);
}

/**
 * @param {HTMLElement} host
 * @param {object} [options]
 */
export function createSvgMercatorEngine(host, options = {}) {
  const listeners = { [MAP_ENGINE_EVENTS.SELECT]: [] };

  host.innerHTML = "";
  const svg = el("svg", {
    id: "map-svg",
    role: "img",
    "aria-label": options.ariaLabel || "可拖动缩放的日本历史地图",
  });
  svg.innerHTML = `
    <defs>
      <pattern id="hatch-dispute" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
        <line x1="0" y1="0" x2="0" y2="8" stroke="currentColor" stroke-width="1.5" opacity="0.55" />
      </pattern>
      <filter id="soft-glow" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="1.2" result="b" />
        <feMerge>
          <feMergeNode in="b" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>
  `;
  const root = el("g", { id: "map-root" });
  const ocean = el("rect", {
    id: "ocean",
    x: -5000,
    y: -5000,
    width: 10000,
    height: 10000,
  });
  const coastG = el("g", { id: "layer-coast" });
  const polityG = el("g", { id: "layer-polities" });
  const disputeG = el("g", { id: "layer-disputes" });
  const markerG = el("g", { id: "layer-markers" });
  const labelG = el("g", { id: "layer-labels" });
  root.append(ocean, coastG, polityG, disputeG, markerG, labelG);
  svg.appendChild(root);
  host.appendChild(svg);

  let scale = 18;
  let tx = 0;
  let ty = 0;
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  let lastCoastKey = "";

  function emit(type, payload) {
    (listeners[type] || []).forEach((fn) => fn(payload));
  }

  function applyTransform() {
    root.setAttribute("transform", `translate(${tx} ${ty}) scale(${scale})`);
  }

  function fitHome() {
    const rect = svg.getBoundingClientRect();
    const width = rect.width || 800;
    const height = rect.height || 600;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    const [x0, y0] = project(128, 46);
    const [x1, y1] = project(146, 24);
    const gw = Math.abs(x1 - x0);
    const gh = Math.abs(y1 - y0);
    const pad = 0.12;
    scale = Math.min(width / (gw * (1 + pad)), height / (gh * (1 + pad)));
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    tx = width / 2 - cx * scale;
    ty = height / 2 - cy * scale;
    applyTransform();
  }

  function setCoastline(geojson) {
    const key = geojson ? JSON.stringify(geojson.type) + String((geojson.coordinates || []).length) : "";
    if (key && key === lastCoastKey && coastG.childNodes.length) return;
    lastCoastKey = key;
    clearGroup(coastG);
    if (!geojson) return;
    const path = el("path", { class: "coast-path", d: geomToPath(geojson) });
    coastG.appendChild(path);
  }

  function drawPolities(polities) {
    clearGroup(polityG);
    (polities || []).forEach((p) => {
      const path = el("path", {
        class: `polity-path is-${p.mode || "direct"}`,
        d: geomToPath(p.geometry),
        fill: p.color || "#4a6741",
      });
      path.dataset.id = p.id;
      path.addEventListener("click", (ev) => {
        ev.stopPropagation();
        emit(MAP_ENGINE_EVENTS.SELECT, { kind: MAP_SELECT_KIND.POLITY, data: p });
      });
      polityG.appendChild(path);
    });
  }

  function drawMarkers(markers, locale = getLocale()) {
    clearGroup(markerG);
    (markers || []).forEach((m) => {
      const [x, y] = project(m.lon, m.lat);
      const attrs = {
        class: `marker ${m.kind || "site"}`,
        transform: `translate(${x} ${y})`,
      };
      if (m.conflict_class) attrs["data-conflict"] = m.conflict_class;
      const g = el("g", attrs);
      const c = el("circle", {
        r: m.kind === "capital" ? 0.22 : 0.16,
        transform: `scale(${1 / scale})`,
      });
      const t = el("text", {
        x: 0.28,
        y: 0.08,
        transform: `scale(${1 / scale})`,
      });
      t.textContent = pickName(m.names, locale) || m.id;
      g.append(c, t);
      g.addEventListener("click", (ev) => {
        ev.stopPropagation();
        emit(MAP_ENGINE_EVENTS.SELECT, { kind: MAP_SELECT_KIND.MARKER, data: m });
      });
      markerG.appendChild(g);
    });
  }

  function drawDisputes(disputes) {
    clearGroup(disputeG);
    (disputes || []).forEach((d) => {
      const lon = d.geometry && d.geometry.lon;
      const lat = d.geometry && d.geometry.lat;
      if (lon == null || lat == null) return;
      const [x, y] = project(lon, lat);
      const g = el("g", {
        class: "dispute-marker",
        transform: `translate(${x} ${y})`,
      });
      const c = el("circle", {
        r: 0.35,
        transform: `scale(${1 / scale})`,
      });
      const t = el("text", {
        "text-anchor": "middle",
        "dominant-baseline": "central",
        transform: `scale(${1 / scale})`,
      });
      t.textContent = "争";
      g.append(c, t);
      g.addEventListener("click", (ev) => {
        ev.stopPropagation();
        emit(MAP_ENGINE_EVENTS.SELECT, { kind: MAP_SELECT_KIND.DISPUTE, data: d });
      });
      disputeG.appendChild(g);
    });
  }

  function setFrame(frame) {
    if (!frame) return;
    const locale = frame.locale || getLocale();
    if (frame.coastline) setCoastline(frame.coastline);
    drawPolities(frame.polities);
    drawMarkers(frame.markers, locale);
    drawDisputes(frame.disputes);
  }

  svg.addEventListener("pointerdown", (ev) => {
    dragging = true;
    lastX = ev.clientX;
    lastY = ev.clientY;
    svg.setPointerCapture(ev.pointerId);
  });
  svg.addEventListener("pointermove", (ev) => {
    if (!dragging) return;
    tx += ev.clientX - lastX;
    ty += ev.clientY - lastY;
    lastX = ev.clientX;
    lastY = ev.clientY;
    applyTransform();
  });
  svg.addEventListener("pointerup", () => {
    dragging = false;
  });
  svg.addEventListener(
    "wheel",
    (ev) => {
      ev.preventDefault();
      const rect = svg.getBoundingClientRect();
      const mx = ev.clientX - rect.left;
      const my = ev.clientY - rect.top;
      const beforeX = (mx - tx) / scale;
      const beforeY = (my - ty) / scale;
      const factor = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
      scale = Math.min(120, Math.max(6, scale * factor));
      tx = mx - beforeX * scale;
      ty = my - beforeY * scale;
      applyTransform();
    },
    { passive: false }
  );

  const onResize = () => fitHome();
  window.addEventListener("resize", onResize);
  fitHome();

  return {
    id: "svg_mercator",
    setFrame,
    fitHome,
    on(type, fn) {
      (listeners[type] || (listeners[type] = [])).push(fn);
    },
    destroy() {
      window.removeEventListener("resize", onResize);
      host.innerHTML = "";
    },
  };
}
