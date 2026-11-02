/**
 * Georeference helpers for Japan_3D_Map.glb under MapLibre mercator space.
 * - fallback: model world XY AABB ↔ WGS84 fallbackBounds (similarity)
 * - refine: ≥3 anchors with model+[lon,lat] → 2D affine (least squares)
 */

const CALIB_URL = new URL("../../../models/Japan_3D_Map.calib.json", import.meta.url);

/**
 * @typedef {{ x: number, y: number, z: number }} Vec3
 * @typedef {{ min: Vec3, max: Vec3 }} Aabb
 * @typedef {{
 *   url: string,
 *   fallbackBounds: { sw: [number, number], ne: [number, number] },
 *   anchors: Array<{ id: string, lon: number, lat: number, model: [number, number, number] | null }>,
 *   altitudeScale?: number,
 *   exaggeration?: number
 * }} TerrainCalib
 */

/** @returns {Promise<TerrainCalib>} */
export async function loadTerrainCalib(url = CALIB_URL.href) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`terrain calib HTTP ${res.status}`);
  return res.json();
}

export function resolveModelUrl(calib, base = CALIB_URL) {
  const rel = (calib && calib.url) || "Japan_3D_Map.glb";
  return new URL(rel, base).href;
}

/**
 * @param {Aabb} aabb
 * @param {{ sw: [number, number], ne: [number, number] }} bounds
 * @param {typeof maplibregl} maplibregl
 * @returns {{ a: number, b: number, c: number, d: number, e: number, f: number, g: number, z0: number }}
 */
export function affineFromAabbBounds(aabb, bounds, maplibregl) {
  const sw = maplibregl.MercatorCoordinate.fromLngLat(
    { lng: bounds.sw[0], lat: bounds.sw[1] },
    0
  );
  const ne = maplibregl.MercatorCoordinate.fromLngLat(
    { lng: bounds.ne[0], lat: bounds.ne[1] },
    0
  );
  const minX = aabb.min.x;
  const maxX = aabb.max.x;
  const minY = aabb.min.y;
  const maxY = aabb.max.y;
  const dx = maxX - minX || 1;
  const dy = maxY - minY || 1;

  // model (minX,minY) → sw, (maxX,maxY) → ne (mercator Y grows north like lat)
  const a = (ne.x - sw.x) / dx;
  const b = 0;
  const c = sw.x - a * minX;
  const d = 0;
  const e = (ne.y - sw.y) / dy;
  const f = sw.y - e * minY;

  const meter = sw.meterInMercatorCoordinateUnits();
  const zSpan = aabb.max.z - aabb.min.z || 1;
  const g = meter; // 1 model-Z unit ≈ 1 meter until exaggeration applied by caller
  const z0 = sw.z - g * aabb.min.z;

  return { a, b, c, d, e, f, g, z0, meterRef: meter };
}

/**
 * Least-squares 2D affine: [mx,my] = [[a,b],[d,e]]·[x,y] + [c,f]
 * Height: mz = z0 + g * modelZ (g from mean meter scale × altitudeScale).
 *
 * @param {Array<{ lon: number, lat: number, model: [number, number, number] }>} anchors
 * @param {typeof maplibregl} maplibregl
 * @param {{ altitudeScale?: number }} [opts]
 */
export function affineFromAnchors(anchors, maplibregl, opts = {}) {
  const usable = (anchors || []).filter(
    (a) =>
      a &&
      Array.isArray(a.model) &&
      a.model.length >= 2 &&
      Number.isFinite(a.lon) &&
      Number.isFinite(a.lat)
  );
  if (usable.length < 3) {
    throw new Error(`need ≥3 anchors with model coords, got ${usable.length}`);
  }

  const xs = usable.map((a) => a.model[0]);
  const ys = usable.map((a) => a.model[1]);
  const mxs = [];
  const mys = [];
  const meters = [];
  usable.forEach((a) => {
    const mc = maplibregl.MercatorCoordinate.fromLngLat(
      { lng: a.lon, lat: a.lat },
      0
    );
    mxs.push(mc.x);
    mys.push(mc.y);
    meters.push(mc.meterInMercatorCoordinateUnits());
  });

  const rowX = solveAffineRow(xs, ys, mxs);
  const rowY = solveAffineRow(xs, ys, mys);

  const altitudeScale = opts.altitudeScale ?? 1;
  const meterMean =
    meters.reduce((s, v) => s + v, 0) / Math.max(1, meters.length);
  const g = meterMean * altitudeScale;

  // Pin z so mean model Z sits on the ellipsoid (z≈0 mercator altitude).
  const zs = usable.map((a) => a.model[2] || 0);
  const zMean = zs.reduce((s, v) => s + v, 0) / zs.length;
  const z0 = -g * zMean;

  return {
    a: rowX[0],
    b: rowX[1],
    c: rowX[2],
    d: rowY[0],
    e: rowY[1],
    f: rowY[2],
    g,
    z0,
    meterRef: meterMean,
    anchorCount: usable.length,
  };
}

/**
 * Prefer anchors when ≥3 have model[]; else AABB ↔ fallbackBounds.
 * @returns {{ affine: object, mode: "anchors" | "bounds", calib: TerrainCalib }}
 */
export function resolveAffine(calib, aabb, maplibregl) {
  const usable = (calib.anchors || []).filter(
    (a) => a && Array.isArray(a.model) && a.model.length >= 2
  );
  const altitudeScale =
    (calib.altitudeScale ?? 1) * (calib.exaggeration ?? 1);

  if (usable.length >= 3) {
    const affine = affineFromAnchors(usable, maplibregl, { altitudeScale });
    return { affine, mode: "anchors", calib };
  }

  const affine = affineFromAabbBounds(
    aabb,
    calib.fallbackBounds,
    maplibregl
  );
  affine.g = (affine.meterRef || affine.g) * altitudeScale;
  // keep z0 consistent with new g relative to aabb.min.z
  const sw = maplibregl.MercatorCoordinate.fromLngLat(
    { lng: calib.fallbackBounds.sw[0], lat: calib.fallbackBounds.sw[1] },
    0
  );
  affine.z0 = sw.z - affine.g * aabb.min.z;
  return { affine, mode: "bounds", calib };
}

/**
 * Column-major 4×4: model (x,y,z,1) → mercator.
 * Ground: affine xy; height: z0 + g*z.
 */
export function affineToMatrix4(affine) {
  const { a, b, c, d, e, f, g, z0 } = affine;
  // THREE.Matrix4 is column-major:
  // x' = a*x + b*y + 0*z + c
  // y' = d*x + e*y + 0*z + f
  // z' = 0*x + 0*y + g*z + z0
  return [
    a,
    d,
    0,
    0,
    b,
    e,
    0,
    0,
    0,
    0,
    g,
    0,
    c,
    f,
    z0,
    1,
  ];
}

export function applyAffinePoint(affine, x, y, z = 0) {
  return {
    x: affine.a * x + affine.b * y + affine.c,
    y: affine.d * x + affine.e * y + affine.f,
    z: affine.z0 + affine.g * z,
  };
}

/** Dump calib-friendly anchors for console paste. */
export function formatAnchorsDump(anchors) {
  return JSON.stringify({ anchors }, null, 2);
}

/**
 * Solve [x y 1] · [a,b,c]^T = t  (least squares).
 * @returns {[number, number, number]}
 */
function solveAffineRow(xs, ys, ts) {
  // Normal equations ATA x = ATb for A rows [x,y,1]
  let sxx = 0;
  let sxy = 0;
  let sx = 0;
  let syy = 0;
  let sy = 0;
  let n = 0;
  let stx = 0;
  let sty = 0;
  let st = 0;
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i];
    const y = ys[i];
    const t = ts[i];
    sxx += x * x;
    sxy += x * y;
    sx += x;
    syy += y * y;
    sy += y;
    n += 1;
    stx += t * x;
    sty += t * y;
    st += t;
  }
  // 3×3 system
  return solve3(
    [
      [sxx, sxy, sx],
      [sxy, syy, sy],
      [sx, sy, n],
    ],
    [stx, sty, st]
  );
}

function solve3(M, b) {
  // Gaussian elimination with partial pivot
  const A = M.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < 3; col++) {
    let pivot = col;
    for (let r = col + 1; r < 3; r++) {
      if (Math.abs(A[r][col]) > Math.abs(A[pivot][col])) pivot = r;
    }
    if (Math.abs(A[pivot][col]) < 1e-18) {
      throw new Error("affine system singular — check anchors");
    }
    if (pivot !== col) {
      const tmp = A[col];
      A[col] = A[pivot];
      A[pivot] = tmp;
    }
    const div = A[col][col];
    for (let c = col; c < 4; c++) A[col][c] /= div;
    for (let r = 0; r < 3; r++) {
      if (r === col) continue;
      const f = A[r][col];
      for (let c = col; c < 4; c++) A[r][c] -= f * A[col][c];
    }
  }
  return [A[0][3], A[1][3], A[2][3]];
}
