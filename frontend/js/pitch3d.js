/* ── PulseXI – True 3D pitch scene (Three.js) ─────────────────────────── */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const PITCH_LENGTH = 24; // world units, goal-to-goal (X axis)
const PITCH_WIDTH = 15;  // world units, touchline-to-touchline (Z axis)

function pctToWorld(xPct, yPct) {
  return {
    x: (xPct / 100 - 0.5) * PITCH_LENGTH,
    z: (yPct / 100 - 0.5) * PITCH_WIDTH,
  };
}

function makeNumberSprite(number) {
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "rgba(10,14,20,0.88)";
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "white";
  ctx.lineWidth = 3;
  ctx.stroke();
  ctx.fillStyle = "white";
  ctx.font = "bold 26px Segoe UI, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(String(number), size / 2, size / 2 + 2);
  const tex = new THREE.CanvasTexture(canvas);
  const mat = new THREE.SpriteMaterial({ map: tex, depthTest: false, sizeAttenuation: true });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(0.55, 0.55, 1);
  return sprite;
}

function buildPitchTexture() {
  const W = 1024, H = 640;
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const ctx = c.getContext("2d");

  const stripes = 12;
  const stripeW = W / stripes;
  for (let i = 0; i < stripes; i++) {
    ctx.fillStyle = i % 2 === 0 ? "#0f5c35" : "#0c4e2e";
    ctx.fillRect(i * stripeW, 0, stripeW, H);
  }

  ctx.strokeStyle = "rgba(255,255,255,0.85)";
  ctx.lineWidth = 4;
  ctx.strokeRect(10, 10, W - 20, H - 20);
  ctx.beginPath(); ctx.moveTo(W / 2, 10); ctx.lineTo(W / 2, H - 10); ctx.stroke();
  ctx.beginPath(); ctx.arc(W / 2, H / 2, 80, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.arc(W / 2, H / 2, 4, 0, Math.PI * 2); ctx.fillStyle = "white"; ctx.fill();

  const boxW = 150, boxH = 320, smallW = 60, smallH = 150;
  ctx.strokeRect(10, H / 2 - boxH / 2, boxW, boxH);
  ctx.strokeRect(W - 10 - boxW, H / 2 - boxH / 2, boxW, boxH);
  ctx.strokeRect(10, H / 2 - smallH / 2, smallW, smallH);
  ctx.strokeRect(W - 10 - smallW, H / 2 - smallH / 2, smallW, smallH);

  ctx.fillStyle = "white";
  ctx.beginPath(); ctx.arc(10 + 100, H / 2, 4, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.arc(W - 10 - 100, H / 2, 4, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.arc(10 + 100, H / 2, 80, -0.9, 0.9); ctx.stroke();
  ctx.beginPath(); ctx.arc(W - 10 - 100, H / 2, 80, Math.PI - 0.9, Math.PI + 0.9); ctx.stroke();

  // corner arcs
  const r = 22;
  ctx.beginPath(); ctx.arc(10, 10, r, 0, Math.PI / 2); ctx.stroke();
  ctx.beginPath(); ctx.arc(W - 10, 10, r, Math.PI / 2, Math.PI); ctx.stroke();
  ctx.beginPath(); ctx.arc(10, H - 10, r, -Math.PI / 2, 0); ctx.stroke();
  ctx.beginPath(); ctx.arc(W - 10, H - 10, r, Math.PI, Math.PI * 1.5); ctx.stroke();

  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = 4;
  return tex;
}

export function initPitch3D(canvas) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x060a10);
  scene.fog = new THREE.Fog(0x060a10, 26, 52);

  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 200);
  const defaultCamPos = new THREE.Vector3(0, 15, 16);
  camera.position.copy(defaultCamPos);

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0.3, 0);
  controls.maxPolarAngle = Math.PI * 0.48;
  controls.minDistance = 7;
  controls.maxDistance = 36;
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.update();

  scene.add(new THREE.AmbientLight(0x88aacc, 0.55));
  const sun = new THREE.DirectionalLight(0xffffff, 1.15);
  sun.position.set(-10, 22, 12);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.camera.left = -18; sun.shadow.camera.right = 18;
  sun.shadow.camera.top = 14; sun.shadow.camera.bottom = -14;
  scene.add(sun);

  const glowA = new THREE.PointLight(0x36d6c6, 0.9, 32);
  glowA.position.set(-15, 9, -9);
  scene.add(glowA);
  const glowB = new THREE.PointLight(0xff9a3c, 0.9, 32);
  glowB.position.set(15, 9, -9);
  scene.add(glowB);

  const pitchMat = new THREE.MeshStandardMaterial({ map: buildPitchTexture(), roughness: 0.92 });
  const pitchMesh = new THREE.Mesh(new THREE.PlaneGeometry(PITCH_LENGTH, PITCH_WIDTH), pitchMat);
  pitchMesh.rotation.x = -Math.PI / 2;
  pitchMesh.receiveShadow = true;
  scene.add(pitchMesh);

  const ball = new THREE.Mesh(
    new THREE.SphereGeometry(0.22, 20, 20),
    new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.35 })
  );
  ball.castShadow = true;
  ball.position.set(0, 0.22, 0);
  scene.add(ball);

  const playerMeshes = {};
  let activePlayerId = null;

  function buildPlayers(playersInfo, homeTeamId) {
    Object.values(playerMeshes).forEach((m) => scene.remove(m.group));
    for (const key in playerMeshes) delete playerMeshes[key];

    Object.entries(playersInfo).forEach(([id, info]) => {
      const isHome = info.teamId === homeTeamId;
      const color = info.isGK ? 0xf4e04d : isHome ? 0x36d6c6 : 0xff9a3c;

      const group = new THREE.Group();
      const body = new THREE.Mesh(
        new THREE.CapsuleGeometry(0.22, 0.46, 4, 10),
        new THREE.MeshStandardMaterial({ color, roughness: 0.5 })
      );
      body.position.y = 0.45;
      body.castShadow = true;
      group.add(body);

      const label = makeNumberSprite(info.number);
      label.position.y = 1.05;
      group.add(label);

      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.34, 0.43, 24),
        new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide, transparent: true, opacity: 0.9 })
      );
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = 0.015;
      ring.visible = false;
      group.add(ring);

      scene.add(group);
      playerMeshes[id] = { group, body, ring, target: { x: 0, z: 0 } };
    });
    activePlayerId = null;
  }

  // updatePlayers/updateBall only set TARGETS -- the actual easing happens
  // every animation frame in animate(), so motion stays smooth and keeps
  // converging even while the match clock itself is paused.
  function updatePlayers(positions, involvedId) {
    for (const [id, p] of Object.entries(positions)) {
      const mesh = playerMeshes[id];
      if (!mesh) continue;
      mesh.target = pctToWorld(p.xPct, p.yPct);
    }
    if (involvedId !== activePlayerId) {
      if (activePlayerId && playerMeshes[activePlayerId]) playerMeshes[activePlayerId].ring.visible = false;
      if (involvedId && playerMeshes[involvedId]) playerMeshes[involvedId].ring.visible = true;
      activePlayerId = involvedId;
    }
  }

  let ballTarget = { x: 0, z: 0 };
  function updateBall(xPct, yPct) {
    ballTarget = pctToWorld(xPct, yPct);
  }

  let followBall = false;
  function setFollowBall(on) { followBall = on; }

  const baseDistance = defaultCamPos.distanceTo(new THREE.Vector3(0, 0.3, 0));
  function getZoomRatio() {
    return baseDistance / camera.position.distanceTo(controls.target);
  }

  function zoomBy(factor) {
    const dir = new THREE.Vector3().subVectors(camera.position, controls.target);
    const dist = Math.max(controls.minDistance, Math.min(controls.maxDistance, dir.length() * factor));
    dir.setLength(dist);
    camera.position.copy(controls.target).add(dir);
    controls.update();
  }

  function resetCamera() {
    camera.position.copy(defaultCamPos);
    controls.target.set(0, 0.3, 0);
    controls.update();
  }

  function resize() {
    const w = canvas.clientWidth || 1;
    const h = canvas.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  function hitTest(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const entries = Object.entries(playerMeshes);
    const hits = raycaster.intersectObjects(entries.map(([, m]) => m.body));
    if (!hits.length) return null;
    const found = entries.find(([, m]) => m.body === hits[0].object);
    return found ? found[0] : null;
  }

  function screenPositionOf(id, worldY = 0.45) {
    const mesh = playerMeshes[id];
    if (!mesh) return null;
    const v = mesh.group.position.clone();
    v.y += worldY;
    v.project(camera);
    const rect = canvas.getBoundingClientRect();
    return { x: (v.x * 0.5 + 0.5) * rect.width, y: (-v.y * 0.5 + 0.5) * rect.height };
  }

  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();

  function animate() {
    requestAnimationFrame(animate);

    for (const mesh of Object.values(playerMeshes)) {
      mesh.group.position.x += (mesh.target.x - mesh.group.position.x) * 0.1;
      mesh.group.position.z += (mesh.target.z - mesh.group.position.z) * 0.1;
    }
    ball.position.x += (ballTarget.x - ball.position.x) * 0.14;
    ball.position.z += (ballTarget.z - ball.position.z) * 0.14;

    if (followBall) {
      controls.target.lerp(new THREE.Vector3(ball.position.x, 0.3, ball.position.z), 0.035);
    }
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  return { buildPlayers, updatePlayers, updateBall, setFollowBall, zoomBy, resetCamera, hitTest, screenPositionOf, getZoomRatio };
}
