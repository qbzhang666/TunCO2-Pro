// three.js viewers: the tunnel model (glTF from /api/geometry, optionally with the TBM at the face)
// and the TBM-type preview on the TBM selection tab.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const ENVELOPE = 10.453;      // common shield envelope of the six Rhino models (m)
const TAIL = 14.8;            // shield tail behind the face in the models (m)
const tbmCache = {};

function matte(root) {
  // trimesh exports metallic PBR materials; without an environment map they render black
  root.traverse(o => { if (o.isMesh) { o.material.metalness = 0; o.material.roughness = 0.75; o.material.side = THREE.DoubleSide; } });
}

function makeViewer(host) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 8000);
  camera.up.set(0, 0, 1);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 2.2));
  const d = new THREE.DirectionalLight(0xffffff, 1.4); d.position.set(10, 20, 15); scene.add(d);
  const d2 = new THREE.DirectionalLight(0xffffff, 0.9); d2.position.set(-15, -10, 8); scene.add(d2);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  const v = { scene, camera, controls, renderer, host: null };
  v.resize = () => {
    const w = v.host?.clientWidth, h = v.host?.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
  };
  const ro = new ResizeObserver(v.resize);
  v.setHost = (el) => { if (!el || el === v.host) return; if (v.host) ro.unobserve(v.host); v.host = el; el.appendChild(renderer.domElement); ro.observe(el); v.resize(); };
  v.setHost(host);
  const loop = () => { requestAnimationFrame(loop); if (v.host?.offsetParent) { controls.update(); renderer.render(scene, camera); } };
  loop();
  v.frame = (box, dir = [0.55, -0.6, 0.35]) => {
    const c = box.getCenter(new THREE.Vector3()), s = Math.max(box.getSize(new THREE.Vector3()).length(), 12);
    controls.target.copy(c);
    camera.position.set(c.x + s * dir[0], c.y + s * dir[1], c.z + s * dir[2]);
    camera.lookAt(c); v.resize();
  };
  return v;
}

async function tbmModel(type) {
  if (!tbmCache[type]) {
    tbmCache[type] = new Promise((ok, bad) => new GLTFLoader().load(`/static/assets/tbm/${type}.glb`, g => { matte(g.scene); ok(g.scene); }, undefined, bad));
  }
  return (await tbmCache[type]).clone(true);
}

// ------------------------------------------------------------------ tunnel model (moves between page slots)
let V, current, tbm, slot = document.querySelector('[data-slot="route"]');
let reqId = 0, framedKey = null, zones = [], selected = null;
const HILITE = new THREE.Color(0xf2b705);
const chMid = (o) => { const x = o.userData?.extras; return x ? (x.ch_from + x.ch_to) / 2 : null; };
function ensureViewer() {
  if (V) return;
  V = makeViewer(slot);
  // click (not drag) picks a zone
  let down = null;
  V.renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; });
  V.renderer.domElement.addEventListener("pointerup", e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4 || !current) return;
    const r = V.renderer.domElement.getBoundingClientRect();
    const ray = new THREE.Raycaster(); ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), V.camera);
    const hit = ray.intersectObject(current, true).find(h => chMid(h.object) != null);
    if (hit) window.dispatchEvent(new CustomEvent("tunco2:zone-picked", { detail: { chainage: chMid(hit.object) } }));
  });
}
function highlight(frame) {
  if (!current) return;
  const z = selected != null ? zones[selected] : null, box = new THREE.Box3();
  current.traverse(o => {
    if (!o.isMesh) return;
    const m = chMid(o), on = z && m != null && m >= z[0] && m <= z[1];
    o.material.emissive?.copy(on ? HILITE : new THREE.Color(0)); if (o.material.emissive) o.material.emissiveIntensity = on ? 0.55 : 0;
    if (on) box.expandByObject(o);
  });
  if (frame && !box.isEmpty()) {
    const c = box.getCenter(new THREE.Vector3()), s = box.getSize(new THREE.Vector3()).length();
    V.frame(box, [0.35, -0.55, 0.28].map(k => k * Math.min(1, 160 / Math.max(s, 1)) * 1.2));
  }
}
async function load(detail) {
  ensureViewer();
  zones = detail.zones || []; selected = detail.selected;
  const my = ++reqId;
  const r = await fetch(`/api/geometry?fmt=glb&rings=${detail.rings}&lod=${detail.lod || 300}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project: detail.project, compat_v1: detail.compat_v1 }) });
  if (!r.ok) return;
  const buf = await r.arrayBuffer();
  const face = (r.headers.get("X-TunCO2-Face") || "").split(",").map(Number);
  if (my !== reqId) return;  // a newer request superseded this one
  new GLTFLoader().parse(buf, "", async (gltf) => {
    if (current) V.scene.remove(current);
    if (tbm) { V.scene.remove(tbm); tbm = null; }
    current = gltf.scene; V.scene.add(current);
    current.traverse(o => { if (o.isMesh) o.material = o.material.clone(); });
    matte(current);
    const key = JSON.stringify([zones, detail.project.route?.alignment?.points?.length, detail.tbm_type]);
    const reframe = key !== framedKey; framedKey = key;
    const type = detail.tbm_type;
    if (type && face.length === 6) {
      const m = await tbmModel(type);
      if (my !== reqId) return;
      const D = detail.project.geometry.tbm_diameter_m, s = D / ENVELOPE;
      const T = new THREE.Vector3(face[3], face[4], face[5]).normalize();
      const Z = new THREE.Vector3(0, 0, 1).addScaledVector(T, -T.z).normalize();
      const Y = new THREE.Vector3().crossVectors(Z, T);
      const P = new THREE.Vector3(face[0], face[1], face[2]).addScaledVector(T, TAIL * s);
      tbm = new THREE.Group(); tbm.add(m);
      tbm.matrixAutoUpdate = false;
      tbm.matrix.makeBasis(T, Y, Z).scale(new THREE.Vector3(s, s, s)).setPosition(P);
      V.scene.add(tbm);
      tbm.matrixWorldNeedsUpdate = true; tbm.updateMatrixWorld(true);
      if (reframe && selected == null) {
        const b = new THREE.Box3().setFromObject(tbm);
        b.expandByPoint(new THREE.Vector3(face[0], face[1], face[2]).addScaledVector(T, -30));
        V.frame(b, [0.6 * T.x - 0.55 * T.y, 0.6 * T.y + 0.55 * T.x, 0.3]);  // from ahead of the face, to one side
      }
    } else if (reframe && selected == null) {
      const box = new THREE.Box3().setFromObject(current);
      if (box.getSize(new THREE.Vector3()).length() > 120 && current.children.length) {
        const first = new THREE.Box3();
        current.children.slice(0, Math.max(1, Math.ceil(current.children.length * 0.04))).forEach(o => first.expandByObject(o));
        V.frame(first);
      } else V.frame(box);
    }
    highlight(reframe && selected != null);
  });
}
window.addEventListener("tunco2:model", (e) => load(e.detail));
window.addEventListener("tunco2:viewer-slot", (e) => { slot = e.detail.el; if (V) V.setHost(slot); });
window.addEventListener("tunco2:select-zone", (e) => { selected = e.detail.index; if (V) highlight(e.detail.frame); });

// ------------------------------------------------------------------ TBM preview
let P, shown, pid = 0;
async function preview(type) {
  const el = document.getElementById("tbmViewer");
  if (!el) return;
  if (!P) P = makeViewer(el);
  requestAnimationFrame(P.resize);
  const my = ++pid;
  const m = await tbmModel(type);
  if (my !== pid) return;
  if (shown) P.scene.remove(shown);
  shown = m; P.scene.add(m);
  P.frame(new THREE.Box3().setFromObject(m), [0.75, -0.9, 0.35]);
}
window.addEventListener("tunco2:tbm-preview", (e) => preview(e.detail.type));
