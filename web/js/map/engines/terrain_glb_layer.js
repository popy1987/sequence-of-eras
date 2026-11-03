/**
 * MapLibre custom layer: Three.js scene hosting Japan_3D_Map.glb under GeoJSON overlays.
 */
import {
  loadTerrainCalib,
  resolveModelUrl,
  resolveLonLatAffine,
  resolveAffine,
  bakeRootToMercator,
  affineToMatrix4,
  formatAnchorsDump,
} from "./terrain_calib.js";

const THREE_MOD = new URL("../../../vendor/three/build/three.module.js", import.meta.url).href;
const GLTF_MOD = new URL("../../../vendor/three/examples/jsm/loaders/GLTFLoader.js", import.meta.url).href;

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
 * Restore the source mesh grid: X=east, Y=north, Z=elevation.
 * The Sketchfab export wraps every tile in the same display transform; keeping
 * that transform makes the AABB heuristic mistake a tilted map plane for up.
 */
function orientSourceGridToMap(THREE, root) {
  root.updateMatrixWorld(true);
  let firstMesh = null;
  root.traverse((obj) => {
    if (!firstMesh && obj.isMesh) firstMesh = obj;
  });
  if (!firstMesh) return root;

  const elements = firstMesh.matrixWorld.elements;
  const elevationScale = Math.hypot(elements[8], elements[9], elements[10]);
  const wrapper = new THREE.Group();
  wrapper.name = "soe-terrain-source-grid";
  wrapper.matrixAutoUpdate = false;
  wrapper.matrix.copy(firstMesh.matrixWorld).invert();
  wrapper.add(root);

  const oriented = new THREE.Group();
  oriented.name = "soe-terrain-orient";
  oriented.scale.z = elevationScale;
  oriented.add(wrapper);
  oriented.updateMatrixWorld(true);
  return oriented;
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

        const light = new THREE.AmbientLight(0xffffff, 1.8);
        scene.add(light);
        const dir = new THREE.DirectionalLight(0xffffff, 0.9);
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
            // glTF 未声明 metalness 时默认为 1；无环境贴图会让地形接近全黑。
            raw.traverse((obj) => {
              if (!obj.isMesh) return;
              const materials = Array.isArray(obj.material)
                ? obj.material
                : [obj.material];
              materials.forEach((material) => {
                if (material && "metalness" in material) {
                  material.metalness = 0;
                }
              });
            });
            modelRoot = orientSourceGridToMap(THREE, raw);
            scene.add(modelRoot);

            const aabb = computeWorldAabb(THREE, modelRoot);
            const lonLat = resolveLonLatAffine(calib, aabb);

            if (calibMode) {
              // Keep source-grid vertices for raycast; preview with legacy
              // mercator affine (warped) so picking stays in model space.
              const legacy = resolveAffine(calib, aabb, maplibregl);
              affineInfo = {
                mode: lonLat.mode,
                placement: "legacy_affine_mercator",
                lonLatAffine: lonLat.lonLatAffine,
                affine: legacy.affine,
                aabb,
              };
              modelMatrix.fromArray(affineToMatrix4(legacy.affine));
              clickHandler = (e) => handleCalibClick(e);
              map.on("click", clickHandler);
              console.info(
                "[terrain_calib] click the 3D mesh to capture model+[lon,lat]. Then atlasAPI.dumpTerrainCalib()"
              );
            } else {
              // Correct placement: lon/lat affine → per-vertex Mercator bake.
              const baked = bakeRootToMercator(
                THREE,
                modelRoot,
                lonLat.lonLatAffine,
                maplibregl
              );
              affineInfo = {
                mode: lonLat.mode,
                placement: "bake_mercator",
                lonLatAffine: lonLat.lonLatAffine,
                aabb,
                vertexCount: baked.vertexCount,
              };
              modelMatrix.identity();
              console.info(
                `[terrain] baked ${baked.vertexCount} verts via ${lonLat.mode} lon/lat affine`
              );
            }

            onReady?.({
              mode: lonLat.mode,
              placement: affineInfo.placement,
              aabb,
              lonLatAffine: lonLat.lonLatAffine,
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
