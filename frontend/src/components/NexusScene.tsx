import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import type { TerminalSnapshotResponse } from "../types/system";
import { formatInr, formatPct } from "../utils/format";

interface NexusSceneProps {
  snapshot: TerminalSnapshotResponse | null;
}

function createRadialGlowTexture(): THREE.CanvasTexture {
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const half = size / 2;
    const gradient = ctx.createRadialGradient(half, half, 0, half, half, half);
    gradient.addColorStop(0, "rgba(255, 255, 255, 1)");
    gradient.addColorStop(0.28, "rgba(255, 255, 255, 0.85)");
    gradient.addColorStop(0.62, "rgba(255, 255, 255, 0.22)");
    gradient.addColorStop(1, "rgba(255, 255, 255, 0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

function generateFibonacciSpherePoints(count: number, radius: number): THREE.Vector3[] {
  const points: THREE.Vector3[] = [];
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i += 1) {
    const y = 1 - (i / Math.max(count - 1, 1)) * 2;
    const radialScale = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = goldenAngle * i;
    const x = Math.cos(theta) * radialScale;
    const z = Math.sin(theta) * radialScale;
    points.push(new THREE.Vector3(x * radius, y * radius, z * radius));
  }
  return points;
}

export function NexusScene({ snapshot }: NexusSceneProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [webglUnavailable, setWebglUnavailable] = useState(false);

  const telemetryRef = useRef({
    killSwitchActive: false,
    riskUtilizationPct: 0,
    openPositionsCount: 0,
  });

  useEffect(() => {
    telemetryRef.current = {
      killSwitchActive: snapshot?.risk.kill_switch_active ?? false,
      riskUtilizationPct: snapshot?.risk.risk_utilization_pct ?? 0,
      openPositionsCount: snapshot?.risk.open_positions_count ?? 0,
    };
  }, [snapshot]);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) {
      return;
    }

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        powerPreference: "high-performance",
        alpha: false,
      });
    } catch {
      setWebglUnavailable(true);
      return;
    }

    const initialWidth = Math.max(container.clientWidth, 320);
    const initialHeight = Math.max(container.clientHeight, 260);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    renderer.setPixelRatio(dpr);
    renderer.setSize(initialWidth, initialHeight);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x020612);
    scene.fog = new THREE.FogExp2(0x020612, 0.055);

    const camera = new THREE.PerspectiveCamera(
      44,
      initialWidth / initialHeight,
      0.1,
      100,
    );
    camera.position.set(0, 0.35, 7.6);

    const composer = new EffectComposer(renderer);
    composer.setPixelRatio(dpr);
    composer.setSize(initialWidth, initialHeight);

    const renderPass = new RenderPass(scene, camera);
    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(initialWidth, initialHeight),
      0.46,
      0.55,
      0.18,
    );
    const outputPass = new OutputPass();
    composer.addPass(renderPass);
    composer.addPass(bloomPass);
    composer.addPass(outputPass);

    // Dynamic cyan, electric blue, and restrained gold point lighting
    const ambientLight = new THREE.AmbientLight(0x0f1f3d, 1.35);
    const cyanLight = new THREE.PointLight(0x22d3ee, 28, 22, 1.6);
    cyanLight.position.set(3.8, 2.2, 3.6);
    const blueLight = new THREE.PointLight(0x3b82f6, 26, 22, 1.6);
    blueLight.position.set(-4.0, -2.0, 2.8);
    const goldLight = new THREE.PointLight(0xd4af37, 16, 20, 1.7);
    goldLight.position.set(0.4, 3.5, -3.2);
    scene.add(ambientLight, cyanLight, blueLight, goldLight);

    const rootGroup = new THREE.Group();
    scene.add(rootGroup);

    const spriteTexture = createRadialGlowTexture();
    const disposables: Array<{ dispose: () => void }> = [spriteTexture];

    // Inner lit lattice core reflecting dynamic cyan/blue/gold lights
    const coreGeometry = new THREE.IcosahedronGeometry(1.48, 2);
    const coreMaterial = new THREE.MeshStandardMaterial({
      color: 0x0a1c3b,
      emissive: 0x071836,
      roughness: 0.28,
      metalness: 0.72,
      wireframe: true,
      transparent: true,
      opacity: 0.38,
    });
    const coreMesh = new THREE.Mesh(coreGeometry, coreMaterial);
    rootGroup.add(coreMesh);
    disposables.push(coreGeometry, coreMaterial);

    // 2,800 core surface particles in Fibonacci distribution
    const CORE_PARTICLES = 2800;
    const SPHERE_RADIUS = 2.15;
    const sphereNodes = generateFibonacciSpherePoints(CORE_PARTICLES, SPHERE_RADIUS);

    const corePositions = new Float32Array(CORE_PARTICLES * 3);
    const coreColors = new Float32Array(CORE_PARTICLES * 3);

    const cCyan = new THREE.Color(0x22d3ee);
    const cBlue = new THREE.Color(0x3b82f6);
    const cWhite = new THREE.Color(0xf8fafc);
    const cGold = new THREE.Color(0xd4af37);
    const workColor = new THREE.Color();

    for (let i = 0; i < CORE_PARTICLES; i += 1) {
      const p = sphereNodes[i];
      const jitter = 0.985 + ((i * 37) % 100) * 0.00035;
      corePositions[i * 3] = p.x * jitter;
      corePositions[i * 3 + 1] = p.y * jitter;
      corePositions[i * 3 + 2] = p.z * jitter;

      const selector = (i * 17) % 100;
      if (selector < 48) {
        workColor.copy(cCyan);
      } else if (selector < 84) {
        workColor.copy(cBlue);
      } else if (selector < 94) {
        workColor.copy(cGold);
      } else {
        workColor.copy(cWhite);
      }
      coreColors[i * 3] = workColor.r;
      coreColors[i * 3 + 1] = workColor.g;
      coreColors[i * 3 + 2] = workColor.b;
    }

    const particleGeometry = new THREE.BufferGeometry();
    particleGeometry.setAttribute(
      "position",
      new THREE.BufferAttribute(corePositions, 3),
    );
    particleGeometry.setAttribute("color", new THREE.BufferAttribute(coreColors, 3));

    const particleMaterial = new THREE.PointsMaterial({
      size: 0.068,
      map: spriteTexture,
      vertexColors: true,
      transparent: true,
      opacity: 0.92,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const corePoints = new THREE.Points(particleGeometry, particleMaterial);
    rootGroup.add(corePoints);
    disposables.push(particleGeometry, particleMaterial);

    // 700 outer telemetry halo particles for volumetric depth (3,500 total particles)
    const HALO_PARTICLES = 700;
    const haloNodes = generateFibonacciSpherePoints(HALO_PARTICLES, SPHERE_RADIUS * 1.38);
    const haloPositions = new Float32Array(HALO_PARTICLES * 3);
    const haloColors = new Float32Array(HALO_PARTICLES * 3);

    for (let i = 0; i < HALO_PARTICLES; i += 1) {
      const p = haloNodes[i];
      const shellScale = 0.92 + ((i * 53) % 100) * 0.0022;
      haloPositions[i * 3] = p.x * shellScale;
      haloPositions[i * 3 + 1] = p.y * shellScale;
      haloPositions[i * 3 + 2] = p.z * shellScale;

      const isGold = i % 7 === 0;
      workColor.copy(isGold ? cGold : cBlue);
      haloColors[i * 3] = workColor.r * 0.85;
      haloColors[i * 3 + 1] = workColor.g * 0.85;
      haloColors[i * 3 + 2] = workColor.b * 0.95;
    }

    const haloGeometry = new THREE.BufferGeometry();
    haloGeometry.setAttribute("position", new THREE.BufferAttribute(haloPositions, 3));
    haloGeometry.setAttribute("color", new THREE.BufferAttribute(haloColors, 3));
    const haloMaterial = new THREE.PointsMaterial({
      size: 0.042,
      map: spriteTexture,
      vertexColors: true,
      transparent: true,
      opacity: 0.45,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const haloPoints = new THREE.Points(haloGeometry, haloMaterial);
    rootGroup.add(haloPoints);
    disposables.push(haloGeometry, haloMaterial);

    // 72 curved QuadraticBezierCurve3 particle connections batched in one LineSegments call
    const ARC_COUNT = 72;
    const SEGMENTS_PER_ARC = 20;
    const lineVertexCount = ARC_COUNT * SEGMENTS_PER_ARC * 2;
    const linePositions = new Float32Array(lineVertexCount * 3);
    const lineColors = new Float32Array(lineVertexCount * 3);

    let cursor = 0;
    for (let a = 0; a < ARC_COUNT; a += 1) {
      const idxStart = (a * 37) % CORE_PARTICLES;
      const idxEnd = (a * 113 + 491) % CORE_PARTICLES;
      const pStart = sphereNodes[idxStart];
      const pEnd = sphereNodes[idxEnd];

      const mid = new THREE.Vector3().addVectors(pStart, pEnd).multiplyScalar(0.5);
      if (mid.lengthSq() < 0.001) {
        mid.set(0, 1, 0);
      }
      const archHeight = SPHERE_RADIUS * (1.18 + (a % 5) * 0.055);
      mid.normalize().multiplyScalar(archHeight);

      const curve = new THREE.QuadraticBezierCurve3(pStart, mid, pEnd);
      const sampled = curve.getPoints(SEGMENTS_PER_ARC);
      const isGoldArc = a % 6 === 0;
      const startColor = isGoldArc ? cGold : cCyan;
      const endColor = isGoldArc ? cCyan : cBlue;

      for (let s = 0; s < SEGMENTS_PER_ARC; s += 1) {
        const ptA = sampled[s];
        const ptB = sampled[s + 1];

        linePositions[cursor * 3] = ptA.x;
        linePositions[cursor * 3 + 1] = ptA.y;
        linePositions[cursor * 3 + 2] = ptA.z;

        const tA = s / SEGMENTS_PER_ARC;
        workColor.copy(startColor).lerp(endColor, tA);
        lineColors[cursor * 3] = workColor.r;
        lineColors[cursor * 3 + 1] = workColor.g;
        lineColors[cursor * 3 + 2] = workColor.b;
        cursor += 1;

        linePositions[cursor * 3] = ptB.x;
        linePositions[cursor * 3 + 1] = ptB.y;
        linePositions[cursor * 3 + 2] = ptB.z;

        const tB = (s + 1) / SEGMENTS_PER_ARC;
        workColor.copy(startColor).lerp(endColor, tB);
        lineColors[cursor * 3] = workColor.r;
        lineColors[cursor * 3 + 1] = workColor.g;
        lineColors[cursor * 3 + 2] = workColor.b;
        cursor += 1;
      }
    }

    const arcGeometry = new THREE.BufferGeometry();
    arcGeometry.setAttribute("position", new THREE.BufferAttribute(linePositions, 3));
    arcGeometry.setAttribute("color", new THREE.BufferAttribute(lineColors, 3));
    const arcMaterial = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.44,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const arcSegments = new THREE.LineSegments(arcGeometry, arcMaterial);
    rootGroup.add(arcSegments);
    disposables.push(arcGeometry, arcMaterial);

    // Subtle precision orbital rings
    const ringGeometry = new THREE.TorusGeometry(2.72, 0.008, 8, 128);
    const ringMaterial = new THREE.MeshBasicMaterial({
      color: 0x22d3ee,
      transparent: true,
      opacity: 0.22,
    });
    const ringOuter = new THREE.Mesh(ringGeometry, ringMaterial);
    ringOuter.rotation.x = Math.PI * 0.38;
    ringOuter.rotation.y = Math.PI * 0.14;
    rootGroup.add(ringOuter);

    const goldRingGeometry = new THREE.TorusGeometry(2.96, 0.006, 8, 128);
    const goldRingMaterial = new THREE.MeshBasicMaterial({
      color: 0xd4af37,
      transparent: true,
      opacity: 0.18,
    });
    const goldRing = new THREE.Mesh(goldRingGeometry, goldRingMaterial);
    goldRing.rotation.x = -Math.PI * 0.28;
    goldRing.rotation.z = Math.PI * 0.2;
    rootGroup.add(goldRing);
    disposables.push(ringGeometry, ringMaterial, goldRingGeometry, goldRingMaterial);

    const pointerTarget = { x: 0, y: 0 };
    const pointerCurrent = { x: 0, y: 0 };

    function handlePointerMove(event: PointerEvent): void {
      if (!container) {
        return;
      }
      const rect = container.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) {
        return;
      }
      const nx = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      const ny = ((event.clientY - rect.top) / rect.height) * 2 - 1;
      pointerTarget.x = nx * 0.24;
      pointerTarget.y = -ny * 0.18;
    }

    container.addEventListener("pointermove", handlePointerMove, { passive: true });

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) {
        return;
      }
      const width = Math.max(Math.floor(entry.contentRect.width), 320);
      const height = Math.max(Math.floor(entry.contentRect.height), 260);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
      composer.setSize(width, height);
    });
    resizeObserver.observe(container);

    let rafId = 0;
    let lastTime = performance.now();

    function animate(now: number): void {
      rafId = window.requestAnimationFrame(animate);
      if (document.hidden) {
        lastTime = now;
        return;
      }

      const dt = Math.min((now - lastTime) / 1000, 0.05);
      lastTime = now;
      const elapsed = now * 0.001;

      const { killSwitchActive, riskUtilizationPct } = telemetryRef.current;
      const spinSpeed = killSwitchActive ? 0.045 : 0.11 + riskUtilizationPct * 0.0012;

      pointerCurrent.x += (pointerTarget.x - pointerCurrent.x) * 0.05;
      pointerCurrent.y += (pointerTarget.y - pointerCurrent.y) * 0.05;

      rootGroup.rotation.y += dt * spinSpeed;
      rootGroup.rotation.x = pointerCurrent.y * 0.8 + Math.sin(elapsed * 0.35) * 0.06;
      rootGroup.rotation.z = pointerCurrent.x * 0.35;

      haloPoints.rotation.y -= dt * 0.055;
      coreMesh.rotation.y -= dt * 0.08;
      ringOuter.rotation.z += dt * 0.09;
      goldRing.rotation.z -= dt * 0.065;

      const breath = 1 + Math.sin(elapsed * 1.4) * 0.014;
      rootGroup.scale.setScalar(breath);

      // Orbit dynamic blue, cyan, and gold lights smoothly
      cyanLight.position.x = Math.cos(elapsed * 0.6) * 4.1;
      cyanLight.position.z = Math.sin(elapsed * 0.6) * 4.1;
      blueLight.position.x = Math.cos(elapsed * 0.45 + 2.1) * 4.3;
      blueLight.position.y = Math.sin(elapsed * 0.45 + 2.1) * 3.1;
      goldLight.position.y = Math.cos(elapsed * 0.52) * 3.6;
      goldLight.position.z = Math.sin(elapsed * 0.52) * 3.6;

      cyanLight.color.setHex(killSwitchActive ? 0xf43f5e : 0x22d3ee);
      arcMaterial.opacity = killSwitchActive
        ? 0.28 + Math.sin(elapsed * 4.0) * 0.08
        : 0.42 + Math.sin(elapsed * 1.8) * 0.06;

      composer.render();
    }

    rafId = window.requestAnimationFrame(animate);

    return () => {
      window.cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      container.removeEventListener("pointermove", handlePointerMove);

      for (const item of disposables) {
        item.dispose();
      }
      composer.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []);

  const equityText = snapshot ? formatInr(snapshot.portfolio.total_equity_inr) : "--";
  const drawdownText = snapshot ? formatPct(snapshot.risk.drawdown_pct) : "--";
  const utilizationText = snapshot ? formatPct(snapshot.risk.risk_utilization_pct) : "--";

  return (
    <section className="nexus-panel relative flex min-h-[380px] flex-col overflow-hidden rounded-lg lg:min-h-[480px]">
      {/* Subtle Corner HUD Header */}
      <div className="pointer-events-none relative z-10 flex items-start justify-between p-4">
        <div>
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-cyan-400">
            NEXUS NEURAL TOPOLOGY CORE
          </span>
          <h2 className="font-display text-sm font-semibold text-white sm:text-base">
            3,500-Node Spot Telemetry Matrix
          </h2>
        </div>

        <div className="flex flex-col items-end gap-1 font-mono text-[11px]">
          <span
            className={`rounded border px-2 py-0.5 ${snapshot?.risk.kill_switch_active
                ? "border-rose-500/50 bg-rose-500/15 text-rose-300"
                : "border-cyan-500/35 bg-cyan-500/10 text-cyan-200"
              }`}
          >
            {snapshot?.risk.kill_switch_active ? "HALTED · KILL SWITCH" : "EXECUTION ARMED (PAPER)"}
          </span>
          <span className="text-[10px] text-slate-400">
            Quote Feed: {snapshot?.portfolio.quote_status === "live" ? "LIVE CCXT" : "STANDBY"}
          </span>
        </div>
      </div>

      {/* Three.js Canvas Mount or Safe Fallback */}
      {webglUnavailable ? (
        <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
          <div className="h-28 w-28 rounded-full border border-cyan-400/50 bg-cyan-500/10 shadow-[0_0_40px_rgba(34,211,238,0.2)]" />
          <p className="mt-4 font-mono text-xs text-cyan-300">
            WebGL hardware context unavailable in this browser session.
          </p>
          <p className="mt-1 max-w-sm text-xs text-slate-400">
            Core paper trading telemetry, risk limits, and FastAPI streams remain fully operational.
          </p>
        </div>
      ) : (
        <div
          ref={mountRef}
          className="absolute inset-0 h-full w-full"
          aria-label="3D Particle Sphere Visualization"
        />
      )}

      {/* Bottom HUD Strip */}
      <div className="pointer-events-none relative z-10 mt-auto grid grid-cols-3 gap-2 border-t border-cyan-500/15 bg-nexus-void/75 px-4 py-2.5 backdrop-blur-sm">
        <div>
          <div className="font-mono text-[10px] uppercase text-slate-400">Virtual Equity</div>
          <div className="font-mono text-xs font-semibold tabular-nums text-white sm:text-sm">
            {equityText}
          </div>
        </div>
        <div>
          <div className="font-mono text-[10px] uppercase text-slate-400">Risk Utilization</div>
          <div className="font-mono text-xs font-semibold tabular-nums text-cyan-300 sm:text-sm">
            {utilizationText}
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono text-[10px] uppercase text-slate-400">Total Drawdown</div>
          <div className="font-mono text-xs font-semibold tabular-nums text-gold-300 sm:text-sm">
            {drawdownText}
          </div>
        </div>
      </div>
    </section>
  );
}
