/**
 * MapLibre custom layer: Three.js scene hosting Japan_3D_Map.glb under GeoJSON overlays.
 */
import {
  loadTerrainCalib,
  resolveModelUrl,
  resolveAffine,
  affineToMatrix4,
  formatAnchorsDump,
} from "./terrain_calib.js";

const THREE_VERSION = "0.160.0";
const THREE_MOD = `https://unpkg.com/three@${THREE_VERSION}/build/three.module.js`;
const GLTF_MOD = `https://unpkg.com/three@${THREE_VERSION}/examples/jsm/loaders/GLTFLoader.js`;

export const TERRAIN_LAYER_ID = "soe-terrain-glb";

let threePromise = null;

function loadThree() {
  if (threePromise) return threePromise;
  threePromise = Promise.all([
    import(/* @vite-ignore */ THREE_MOD),
    import(/* @vite-ignore */ GLTF_MOD),
  ]).then(([THREE, gltfMod]) => ({
    THREE,
    GLTFLoader: gltfMod.GLTFLoader,
  }));
  return threePromise;
}

/**
 * World-space AABB of an Object3D after matrices are current.
 * @param {*} THREE
 * @param {*} root
 */
function computeWorldAabb(THREE, root) {
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) {
    return {
      min: { x: -0.5, y: -0.5, z: 0 },
      max: { x: 0.5, y: 0.5, z: 0.02 },
    };
  }
  return {
    min: { x: box.min.x, y: box.min.y, z: box.min.z },
    max: { x: box.max.x, y: box.max.y, z: box.max.z },
  };
}

/**
 * Sketchfab/OSG exports often leave "up" on X or Y. Rotate so the thinnest
 * AABB axis becomes +Z (height), leaving XY as the map plane for calib.
 */
function orientThinnestAxisToZ(THREE, root) {
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  const size = new THREE.Vector3();
  box.getSize(size);
  const dims = [
    { axis: "x", len: size.x },
    { axis: "y", len: size.y },
    { axis: "z", len: size.z },
  ].sort((a, b) => a.len - b.len);
  const up = dims[0].axis;
  if (up === "z") return root;

  const wrapper = new THREE.Group();
  wrapper.name = "soe-terrain-orient";
  if (up === "x") {
    // +X up → +Z up: rotate -90° about Y
    wrapper.rotation.y = -Math.PI / 2;
  } else {
    // +Y up → +Z up: rotate +90° about X
    wrapper.rotation.x = Math.PI / 2;
  }
  wrapper.add(root);
  wrapper.updateMatrixWorld(true);
  return wrapper;
}

/**
 * @param {object} options
 * @param {typeof maplibregl} options.maplibregl
 * @param {boolean} [options.calibMode]
 * @param {(p: { loaded: number, total: number, pct: number }) => void} [options.onProgress]
 * @param {(info: object) => void} [options.onReady]
 * @param {(err: Error) => void} [options.onError]
 * @param {(sample: object) => void} [options.onCalibSample]
 */
export function createTerrainGlbLayer(options = {}) {
  const {
    maplibregl,
    calibMode = false,
    onProgress,
    onReady,
    onError,
    onCalibSample,
  } = options;

  let map = null;
  let renderer = null;
  let scene = null;
  let camera = null;
  let modelRoot = null;
  let modelMatrix = null;
  let THREE = null;
  let raycaster = null;
  let pointer = null;
  let calib = null;
  let affineInfo = null;
  let calibSamples = [];
  let destroyed = false;
  let clickHandler = null;

  const api = {
    id: TERRAIN_LAYER_ID,
    type: "custom",
    renderingMode: "3d",

    getCalib() {
      return calib;
    },
    getAffineInfo() {
      return affineInfo;
    },
    getCalibSamples() {
      return calibSamples.slice();
    },
    dumpTerrainCalib() {
      const anchors = (calib?.anchors || []).map((a) => {
        const hit = calibSamples.find((s) => s.id === a.id);
        return {
          ...a,
          model: hit?.model ?? a.model,
        };
      });
      // Also include unnamed extra samples
      const extras = calibSamples
        .filter((s) => !anchors.some((a) => a.id === s.id))
        .map((s) => ({
          id: s.id,
          lon: s.lon,
          lat: s.lat,
          model: s.model,
        }));
      return formatAnchorsDump([...anchors, ...extras]);
    },

    async onAdd(mapInstance, gl) {
      map = mapInstance;
      try {
        const mods = await loadThree();
        if (destroyed) return;
        THREE = mods.THREE;
        const { GLTFLoader } = mods;

        camera = new THREE.Camera();
        scene = new THREE.Scene();
        raycaster = new THREE.Raycaster();
        pointer = new THREE.Vector2();

        const light = new THREE.AmbientLight(0xffffff, 0.85);
        scene.add(light);
        const dir = new THREE.DirectionalLight(0xffffff, 0.65);
        dir.position.set(0.4, 0.8, 1).normalize();
        scene.add(dir);

        renderer = new THREE.WebGLRenderer({
          canvas: map.getCanvas(),
          context: gl,
          antialias: true,
        });
        renderer.autoClear = false;
        renderer.outputColorSpace = THREE.SRGBColorSpace;

        modelMatrix = new THREE.Matrix4();

        calib = await loadTerrainCalib();
        if (destroyed) return;
        const modelUrl = resolveModelUrl(calib);

        const loader = new GLTFLoader();
        loader.load(
          modelUrl,
          (gltf) => {
            if (destroyed) return;
            const raw = gltf.scene || gltf.scenes[0];
            modelRoot = orientThinnestAxisToZ(THREE, raw);
            scene.add(modelRoot);

            const aabb = computeWorldAabb(THREE, modelRoot);
            const resolved = resolveAffine(calib, aabb, maplibregl);
            affineInfo = {
              mode: resolved.mode,
              affine: resolved.affine,
              aabb,
            };
            modelMatrix.fromArray(affineToMatrix4(resolved.affine));

            if (calibMode) {
              clickHandler = (e) => handleCalibClick(e);
              map.on("click", clickHandler);
              console.info(
                "[terrain_calib] click the 3D mesh to capture model+[lon,lat]. Then atlasAPI.dumpTerrainCalib()"
              );
            }

            onReady?.({
              mode: resolved.mode,
              aabb,
              affine: resolved.affine,
              calib,
            });
            map.triggerRepaint();
          },
          (xhr) => {
            if (!xhr || !xhr.total) return;
            const pct = Math.min(100, Math.round((100 * xhr.loaded) / xhr.total));
            onProgress?.({
              loaded: xhr.loaded,
              total: xhr.total,
              pct,
            });
          },
          (err) => {
            const error =
              err instanceof Error ? err : new Error(String(err?.message || err));
            console.error("[terrain] GLB load failed", error);
            onError?.(error);
          }
        );
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err));
        console.error("[terrain] init failed", error);
        onError?.(error);
      }
    },

    render(_gl, matrix) {
      if (!renderer || !scene || !camera || !modelMatrix) return;
      const m = new THREE.Matrix4().fromArray(matrix);
      camera.projectionMatrix = m.multiply(modelMatrix);
      renderer.resetState();
      renderer.render(scene, camera);
      map.triggerRepaint();
    },

    onRemove() {
      destroyed = true;
      if (map && clickHandler) {
        map.off("click", clickHandler);
        clickHandler = null;
      }
      if (modelRoot && scene) {
        scene.remove(modelRoot);
      }
      modelRoot = null;
      // Do not dispose the shared map canvas GL context via renderer.dispose()
      // in a way that breaks MapLibre; just drop references.
      renderer = null;
      scene = null;
      camera = null;
      map = null;
    },
  };

  function handleCalibClick(e) {
    if (!modelRoot || !camera || !renderer || !THREE) return;
    const canvas = map.getCanvas();
    const rect = canvas.getBoundingClientRect();
    // MapLibre point is CSS px relative to the canvas; geo from lngLat, model from raycast.
    pointer.x = (e.point.x / canvas.clientWidth) * 2 - 1;
    pointer.y = -(e.point.y / canvas.clientHeight) * 2 + 1;

    // Build a picking ray in model space: inverse of projectionMatrix maps NDC → model
    const inv = camera.projectionMatrix.clone().invert();
    const near = new THREE.Vector3(pointer.x, pointer.y, -1).applyMatrix4(inv);
    const far = new THREE.Vector3(pointer.x, pointer.y, 1).applyMatrix4(inv);
    const origin = near;
    const dir = far.clone().sub(near).normalize();
    raycaster.set(origin, dir);

    const hits = raycaster.intersectObject(modelRoot, true);
    if (!hits.length) {
      console.info("[terrain_calib] miss — click the terrain mesh");
      return;
    }
    const p = hits[0].point;
    const sample = {
      id: `sample_${calibSamples.length + 1}`,
      lon: e.lngLat.lng,
      lat: e.lngLat.lat,
      model: [round6(p.x), round6(p.y), round6(p.z)],
      css: { x: e.point.x, y: e.point.y, w: rect.width, h: rect.height },
    };

    // Snap to nearest named anchor without model if within ~1.2° 
    const empty = (calib?.anchors || []).filter((a) => !a.model);
    let best = null;
    let bestD = Infinity;
    empty.forEach((a) => {
      const d =
        (a.lon - sample.lon) * (a.lon - sample.lon) +
        (a.lat - sample.lat) * (a.lat - sample.lat);
      if (d < bestD) {
        bestD = d;
        best = a;
      }
    });
    if (best && bestD < 1.2 * 1.2) {
      sample.id = best.id;
      sample.lon = best.lon;
      sample.lat = best.lat;
      sample.snappedTo = best.id;
      // replace prior sample for same id
      calibSamples = calibSamples.filter((s) => s.id !== best.id);
    }

    calibSamples.push(sample);
    console.info("[terrain_calib] sample", sample);
    console.info(
      `[terrain_calib] ${calibSamples.length} sample(s). atlasAPI.dumpTerrainCalib()`
    );
    onCalibSample?.(sample);
  }

  return api;
}

function round6(n) {
  return Math.round(n * 1e6) / 1e6;
}
