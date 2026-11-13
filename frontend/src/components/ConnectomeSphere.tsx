import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { TriangularOpportunity } from "../types/arbitrage";

interface ConnectomeSphereProps {
  topOpportunity: TriangularOpportunity | null;
  totalMarkets: number;
  yawDeg: number;
}

export function ConnectomeSphere({
  topOpportunity,
  totalMarkets,
  yawDeg,
}: ConnectomeSphereProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 640;
    const height = container.clientHeight || 480;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x030712); // Deep obsidian void

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(0, 0, 360);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      return;
    }

    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    // Root rotating group
    const rootGroup = new THREE.Group();
    scene.add(rootGroup);

    // 1. Generate Fibonacci spherical points for 54 market nodes
    const nodeCount = Math.max(totalMarkets, 54);
    const radius = 110;
    const nodePositions: THREE.Vector3[] = [];
    const goldenRatio = (1 + Math.sqrt(5)) / 2;

    for (let i = 0; i < nodeCount; i++) {
      const theta = (2 * Math.PI * i) / goldenRatio;
      const phi = Math.acos(1 - (2 * (i + 0.5)) / nodeCount);
      const x = radius * Math.sin(phi) * Math.cos(theta);
      const y = radius * Math.sin(phi) * Math.sin(theta);
      const z = radius * Math.cos(phi);
      nodePositions.push(new THREE.Vector3(x, y, z));
    }

    // 2. Nodes point cloud
    const nodeGeometry = new THREE.BufferGeometry().setFromPoints(nodePositions);
    const nodeMaterial = new THREE.PointsMaterial({
      size: 4.5,
      color: 0x00e5ff,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
    });
    const nodePoints = new THREE.Points(nodeGeometry, nodeMaterial);
    rootGroup.add(nodePoints);

    // 3. Connectome curved strands (Quadratic Bezier curves between nodes)
    const curvePoints: THREE.Vector3[] = [];
    const curveColors: number[] = [];

    const cyanColor = new THREE.Color(0x00e5ff);
    const goldColor = new THREE.Color(0xffb300);
    const purpleColor = new THREE.Color(0x8b5cf6);
    const blueColor = new THREE.Color(0x3b82f6);

    const colorsPalette = [cyanColor, goldColor, purpleColor, blueColor];

    for (let i = 0; i < nodePositions.length; i++) {
      // Connect each node to 3-4 nearest/random neighbors
      const neighbors = [(i + 3) % nodePositions.length, (i + 7) % nodePositions.length, (i + 13) % nodePositions.length];
      for (const targetIdx of neighbors) {
        const p1 = nodePositions[i];
        const p2 = nodePositions[targetIdx];

        // Midpoint pulled inward/outward for torus curvature
        const mid = new THREE.Vector3().addVectors(p1, p2).multiplyScalar(0.5);
        const normal = mid.clone().normalize();
        const control = mid.clone().add(normal.multiplyScalar(Math.sin(i) * 35));

        const curve = new THREE.QuadraticBezierCurve3(p1, control, p2);
        const sampled = curve.getPoints(12);

        const chosenColor = colorsPalette[(i + targetIdx) % colorsPalette.length];
        for (let j = 0; j < sampled.length - 1; j++) {
          curvePoints.push(sampled[j], sampled[j + 1]);
          curveColors.push(chosenColor.r, chosenColor.g, chosenColor.b);
          curveColors.push(chosenColor.r, chosenColor.g, chosenColor.b);
        }
      }
    }

    const lineGeometry = new THREE.BufferGeometry().setFromPoints(curvePoints);
    lineGeometry.setAttribute("color", new THREE.Float32BufferAttribute(curveColors, 3));

    const lineMaterial = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
    });

    const connectomeLines = new THREE.LineSegments(lineGeometry, lineMaterial);
    rootGroup.add(connectomeLines);

    // 4. Subtle inner wireframe sphere
    const sphereGeo = new THREE.SphereGeometry(radius * 0.98, 24, 24);
    const sphereWireMat = new THREE.MeshBasicMaterial({
      color: 0x0ea5e9,
      wireframe: true,
      transparent: true,
      opacity: 0.04,
    });
    const wireSphere = new THREE.Mesh(sphereGeo, sphereWireMat);
    rootGroup.add(wireSphere);

    // Animation loop
    let animationFrameId: number;
    let currentAngle = 0;

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      currentAngle += 0.0035;
      rootGroup.rotation.y = currentAngle;
      rootGroup.rotation.x = Math.sin(currentAngle * 0.5) * 0.15;
      renderer.render(scene, camera);
    };

    animate();

    const handleResize = () => {
      if (!container) return;
      const w = container.clientWidth || 640;
      const h = container.clientHeight || 480;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };

    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);
      renderer.dispose();
      lineGeometry.dispose();
      lineMaterial.dispose();
      nodeGeometry.dispose();
      nodeMaterial.dispose();
      sphereGeo.dispose();
      sphereWireMat.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [totalMarkets]);

  const candidate = topOpportunity || {
    id: "ARB-TRI-01",
    path: "USDT -> BTC -> ETH -> USDT",
    gross_edge_bps: 14.8,
    net_edge_bps: -2.4,
    quality_score: 0.994,
    status: "ACTIVE",
  };

  return (
    <div className="relative h-full min-h-[380px] w-full overflow-hidden rounded-lg border border-cyan-500/25 bg-black/60 shadow-2xl">
      {/* Three.js canvas container */}
      <div ref={mountRef} className="absolute inset-0 h-full w-full" />

      {/* Top degree & axis indicators */}
      <div className="pointer-events-none absolute top-3 right-4 font-mono text-[11px] text-cyan-400/80">
        SPIN {yawDeg.toFixed(1)}° · AXIS LOCK
      </div>

      {/* Left degree markers */}
      <div className="pointer-events-none absolute top-6 left-3 space-y-16 font-mono text-[10px] text-cyan-500/50">
        <div>- 0 DEG</div>
        <div>- 85 DEG</div>
        <div>- 169 DEG</div>
        <div>- 254 DEG</div>
        <div>- 339 DEG</div>
      </div>

      {/* Stanford / Claude Target Reticle HUD Overlay */}
      <div className="pointer-events-none absolute bottom-5 left-5 max-w-sm rounded-sm border border-amber-500/80 bg-black/85 p-2.5 font-mono shadow-[0_0_15px_rgba(245,158,11,0.25)] backdrop-blur-md">
        <div className="flex items-center justify-between text-[11px] text-amber-400">
          <span className="font-bold tracking-wider">
            CANDIDATE {candidate.id}
          </span>
          <span className="text-[10px] text-amber-300/80">
            SHA-256 0x8F · SOTA {candidate.quality_score.toFixed(3)}
          </span>
        </div>
        <div className="mt-1 text-[10px] text-slate-300">
          <span className="text-cyan-400">PATH:</span> {candidate.path}
        </div>
        <div className="mt-0.5 flex items-center justify-between text-[10px]">
          <span className="text-emerald-400 font-bold">
            GROSS EDGE: {candidate.gross_edge_bps > 0 ? "+" : ""}
            {candidate.gross_edge_bps.toFixed(2)} BPS
          </span>
          <span
            className={
              candidate.net_edge_bps > 0
                ? "text-cyan-300 font-bold"
                : "text-amber-400/90"
            }
          >
            NET: {candidate.net_edge_bps > 0 ? "+" : ""}
            {candidate.net_edge_bps.toFixed(2)} BPS
          </span>
        </div>
        <div className="mt-1 text-[9px] text-slate-400 uppercase tracking-tight">
          OPUS PLAN: CYPHER MCTS HOP | CROWLLM ADVISORY CODE-GEN
        </div>
      </div>
    </div>
  );
}

