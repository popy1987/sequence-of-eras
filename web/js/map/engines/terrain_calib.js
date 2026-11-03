/**
 * Georeference helpers for Japan_3D_Map.glb under MapLibre mercator space.
 *
 * The Sketchfab Japan mesh is authored on a near-linear lon/lat (plate-carrée)
 * grid. Mapping that grid with a single affine into Web Mercator warps the
 * islands (especially N–S) — residuals that cannot be fixed by translate/scale.
 *
 * Correct path: affine model XY → lon/lat, then bake each vertex through
 * MercatorCoordinate.fromLngLat into mercator space (identity modelMatrix).
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
 * @typedef {{
 *   a: number, b: number, c: number,
 *   d: number, e: number, f: number,
 *   altitudeScale: number,
 *   zRef: number,
 *   anchorCount?: number
 * }} LonLatAffine
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

function usableAnchors(anchors) {
  return (anchors || []).filter(
    (a) =>
      a &&
      Array.isArray(a.model) &&
      a.model.length >= 2 &&
      Number.isFinite(a.lon) &&
      Number.isFinite(a.lat)
  );
}

/**
 * Least-squares: lon = a*x + b*y + c, lat = d*x + e*y + f
 * (model XY is the source grid after orientSourceGridToMap).
 */
export function lonLatAffineFromAnchors(anchors, opts = {}) {
  const usable = usableAnchors(anchors);
  if (usable.length < 3) {
    throw new Error(`need ≥3 anchors with model coords, got ${usable.length}`);
  }
  const xs = usable.map((a) => a.model[0]);
  const ys = usable.map((a) => a.model[1]);
  const lons = usable.map((a) => a.lon);
  const lats = usable.map((a) => a.lat);
  const rowLon = solveAffineRow(xs, ys, lons);
  const rowLat = solveAffineRow(xs, ys, lats);
  const zs = usable.map((a) => a.model[2] || 0);
  const zRef = zs.reduce((s, v) => s + v, 0) / zs.length;
  return {
    a: rowLon[0],
    b: rowLon[1],
    c: rowLon[2],
    d: rowLat[0],
    e: rowLat[1],
    f: rowLat[2],
    altitudeScale: opts.altitudeScale ?? 1,
    zRef,
    anchorCount: usable.length,
  };
}

/** AABB XY ↔ fallbackBounds as lon/lat (similarity, no shear). */
export function lonLatAffineFromAabbBounds(aabb, bounds, opts = {}) {
  const minX = aabb.min.x;
  const maxX = aabb.max.x;
  const minY = aabb.min.y;
  const maxY = aabb.max.y;
  const dx = maxX - minX || 1;
  const dy = maxY - minY || 1;
  const lon0 = bounds.sw[0];
  const lon1 = bounds.ne[0];
  const lat0 = bounds.sw[1];
  const lat1 = bounds.ne[1];
  const a = (lon1 - lon0) / dx;
  const e = (lat1 - lat0) / dy;
  return {
    a,
    b: 0,
    c: lon0 - a * minX,
    d: 0,
    e,
    f: lat0 - e * minY,
    altitudeScale: opts.altitudeScale ?? 1,
    zRef: aabb.min.z,
  };
}

/**
 * Prefer ≥3 anchors → lon/lat affine; else AABB ↔ fallbackBounds.
 * @returns {{ lonLatAffine: LonLatAffine, mode: "anchors" | "bounds", calib: TerrainCalib }}
 */
export function resolveLonLatAffine(calib, aabb) {
  const altitudeScale =
    (calib.altitudeScale ?? 1) * (calib.exaggeration ?? 1);
  const usable = usableAnchors(calib.anchors);
  if (usable.length >= 3) {
    return {
      lonLatAffine: lonLatAffineFromAnchors(usable, { altitudeScale }),
      mode: "anchors",
      calib,
    };
  }
  return {
    lonLatAffine: lonLatAffineFromAabbBounds(aabb, calib.fallbackBounds, {
      altitudeScale,
    }),
    mode: "bounds",
    calib,
  };
}

export function applyLonLatAffine(aff, x, y) {
  return {
    lon: aff.a * x + aff.b * y + aff.c,
    lat: aff.d * x + aff.e * y + aff.f,
  };
}

/**
 * Legacy: single affine model → mercator (warps N–S). Kept for ?terrain_calib=1
 * so raycasts stay in source-grid space while previewing.
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
  const a = (ne.x - sw.x) / dx;
  const e = (ne.y - sw.y) / dy;
  const meter = sw.meterInMercatorCoordinateUnits();
  return {
    a,
    b: 0,
    c: sw.x - a * minX,
    d: 0,
    e,
    f: sw.y - e * minY,
    g: meter,
    z0: sw.z - meter * aabb.min.z,
    meterRef: meter,
  };
}

export function affineFromAnchors(anchors, maplibregl, opts = {}) {
  const usable = usableAnchors(anchors);
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
  const zs = usable.map((a) => a.model[2] || 0);
  const zMean = zs.reduce((s, v) => s + v, 0) / zs.length;
  return {
    a: rowX[0],
    b: rowX[1],
    c: rowX[2],
    d: rowY[0],
    e: rowY[1],
    f: rowY[2],
    g,
    z0: -g * zMean,
    meterRef: meterMean,
    anchorCount: usable.length,
  };
}

/** @deprecated use resolveLonLatAffine + bakeRootToMercator */
export function resolveAffine(calib, aabb, maplibregl) {
  const altitudeScale =
    (calib.altitudeScale ?? 1) * (calib.exaggeration ?? 1);
  const usable = usableAnchors(calib.anchors);
  if (usable.length >= 3) {
    return {
      affine: affineFromAnchors(usable, maplibregl, { altitudeScale }),
      mode: "anchors",
      calib,
    };
  }
  const affine = affineFromAabbBounds(aabb, calib.fallbackBounds, maplibregl);
  affine.g = (affine.meterRef || affine.g) * altitudeScale;
  const sw = maplibregl.MercatorCoordinate.fromLngLat(
    { lng: calib.fallbackBounds.sw[0], lat: calib.fallbackBounds.sw[1] },
    0
  );
  affine.z0 = sw.z - affine.g * aabb.min.z;
  return { affine, mode: "bounds", calib };
}

export function affineToMatrix4(affine) {
  const { a, b, c, d, e, f, g, z0 } = affine;
  return [a, d, 0, 0, b, e, 0, 0, 0, 0, g, 0, c, f, z0, 1];
}

export function applyAffinePoint(affine, x, y, z = 0) {
  return {
    x: affine.a * x + affine.b * y + affine.c,
    y: affine.d * x + affine.e * y + affine.f,
    z: affine.z0 + affine.g * z,
  };
}

export function formatAnchorsDump(anchors) {
  return JSON.stringify({ anchors }, null, 2);
}

/**
 * Bake mesh vertices from source-grid space into MapLibre mercator units.
 * Flattens world transforms into positions and resets local matrices so the
 * custom layer can use an identity modelMatrix.
 *
 * @param {*} THREE
 * @param {*} root oriented source-grid root
 * @param {LonLatAffine} lonLatAffine
 * @param {typeof maplibregl} maplibregl
 * @returns {{ vertexCount: number, lonLatAffine: LonLatAffine }}
 */
export function bakeRootToMercator(THREE, root, lonLatAffine, maplibregl) {
  root.updateMatrixWorld(true);
  const v = new THREE.Vector3();
  let vertexCount = 0;
  const altitudeScale = lonLatAffine.altitudeScale || 1;
  const zRef = lonLatAffine.zRef || 0;

  root.traverse((obj) => {
    if (!obj.isMesh || !obj.geometry) return;
    // Clone so shared GLTF geometries are not double-baked across meshes.
    const geom = obj.geometry.clone();
    obj.geometry = geom;
    const pos = geom.attributes.position;
    if (!pos) return;

    const baked = pos.clone();
    const mw = obj.matrixWorld;

    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i);
      v.applyMatrix4(mw);
      const { lon, lat } = applyLonLatAffine(lonLatAffine, v.x, v.y);
      const elevMeters = (v.z - zRef) * altitudeScale;
      const mc = maplibregl.MercatorCoordinate.fromLngLat(
        { lng: lon, lat },
        elevMeters
      );
      baked.setXYZ(i, mc.x, mc.y, mc.z);
      vertexCount += 1;
    }
    baked.needsUpdate = true;
    geom.setAttribute("position", baked);
    geom.computeVertexNormals();
    geom.computeBoundingSphere();
    geom.computeBoundingBox();

    obj.matrixAutoUpdate = false;
    obj.matrix.identity();
    obj.matrixWorld.identity();
  });

  // Neutralize group transforms so scene stays in mercator units.
  root.traverse((obj) => {
    if (obj.isMesh) return;
    obj.matrixAutoUpdate = false;
    obj.position.set(0, 0, 0);
    obj.quaternion.identity();
    obj.scale.set(1, 1, 1);
    obj.matrix.identity();
    obj.matrixWorld.identity();
  });
  root.updateMatrixWorld(true);

  return { vertexCount, lonLatAffine };
}

function solveAffineRow(xs, ys, ts) {
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
