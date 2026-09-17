"use client";

import { useMemo, useRef, useSyncExternalStore } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

/**
 * ModelConvergence — the HELIOS concept rendered literally, not decoratively.
 *
 *   GFS ┐
 *   IFS ┼──▶  HELIOS core  ──▶  one verified forecast
 *   ICON┘
 *
 * Three spectral streams (GFS blue, IFS violet, ICON teal) flow inward along
 * curved paths, converge on a warm amber core, which emits a single calibrated
 * forecast line to the right. Procedural — no image sequence, no external
 * assets. Follows the project UI/UX skill's Three.js rules: one renderer,
 * DPR capped at 2, geometry/material disposal on unmount (R3F handles this for
 * declarative primitives), and a full reduced-motion static fallback.
 */

const MODEL_COLORS = {
  gfs: "#4da3ff",
  ifs: "#8b7cff",
  icon: "#2fd6b4",
  helios: "#ffc773",
  heliosCore: "#fff2d6",
} as const;

function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
}

/** A single model → core stream: a tube along a quadratic bezier with a
 *  travelling brightness pulse driven by a dashed opacity gradient. */
function Stream({
  from,
  color,
  phase,
}: {
  from: [number, number, number];
  color: string;
  phase: number;
}) {
  const matRef = useRef<THREE.MeshBasicMaterial>(null);
  const pulseRef = useRef<THREE.Mesh>(null);

  const { curve, geometry } = useMemo(() => {
    const start = new THREE.Vector3(...from);
    const control = new THREE.Vector3(from[0] * 0.35, from[1] * 0.15, 0.6);
    const end = new THREE.Vector3(0, 0, 0);
    const c = new THREE.QuadraticBezierCurve3(start, control, end);
    const g = new THREE.TubeGeometry(c, 48, 0.012, 8, false);
    return { curve: c, geometry: g };
  }, [from]);

  useFrame(({ clock }) => {
    const t = (clock.elapsedTime * 0.35 + phase) % 1;
    if (pulseRef.current) {
      const p = curve.getPointAt(t);
      pulseRef.current.position.set(p.x, p.y, p.z);
      const s = 0.6 + 0.4 * Math.sin(t * Math.PI); // fade near ends
      pulseRef.current.scale.setScalar(s);
    }
    if (matRef.current) {
      matRef.current.opacity = 0.28 + 0.12 * Math.sin(clock.elapsedTime * 1.2 + phase * 6);
    }
  });

  return (
    <group>
      <mesh geometry={geometry}>
        <meshBasicMaterial
          ref={matRef}
          color={color}
          transparent
          opacity={0.32}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      {/* travelling energy pulse */}
      <mesh ref={pulseRef}>
        <sphereGeometry args={[0.03, 12, 12]} />
        <meshBasicMaterial color={color} transparent opacity={0.9} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
    </group>
  );
}

/** The warm HELIOS synthesis core: layered additive spheres with a soft breath. */
function HeliosCore() {
  const g = useRef<THREE.Group>(null);
  const halo = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    const b = 1 + 0.06 * Math.sin(clock.elapsedTime * 1.6);
    if (g.current) g.current.scale.setScalar(b);
    if (halo.current) {
      const m = halo.current.material as THREE.MeshBasicMaterial;
      m.opacity = 0.14 + 0.06 * Math.sin(clock.elapsedTime * 1.6);
    }
  });
  return (
    <group ref={g}>
      <mesh ref={halo}>
        <sphereGeometry args={[0.42, 24, 24]} />
        <meshBasicMaterial color={MODEL_COLORS.helios} transparent opacity={0.16} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.16, 24, 24]} />
        <meshBasicMaterial color={MODEL_COLORS.helios} transparent opacity={0.55} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.075, 20, 20]} />
        <meshBasicMaterial color={MODEL_COLORS.heliosCore} />
      </mesh>
    </group>
  );
}

/** The single emitted, verified forecast line leaving the core to the right. */
function ForecastEmission() {
  const matRef = useRef<THREE.MeshBasicMaterial>(null);
  const glowRef = useRef<THREE.MeshBasicMaterial>(null);
  const pulseRef = useRef<THREE.Mesh>(null);
  const { curve, geometry, glowGeometry } = useMemo(() => {
    const c = new THREE.QuadraticBezierCurve3(
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0.9, 0.05, 0.2),
      new THREE.Vector3(1.9, 0.12, 0),
    );
    const g = new THREE.TubeGeometry(c, 48, 0.024, 10, false);
    const gg = new THREE.TubeGeometry(c, 48, 0.055, 10, false);
    return { curve: c, geometry: g, glowGeometry: gg };
  }, []);
  useFrame(({ clock }) => {
    const t = (clock.elapsedTime * 0.5) % 1;
    if (pulseRef.current) {
      const p = curve.getPointAt(t);
      pulseRef.current.position.set(p.x, p.y, p.z);
    }
    const b = 0.72 + 0.16 * Math.sin(clock.elapsedTime * 1.4);
    if (matRef.current) matRef.current.opacity = b;
    if (glowRef.current) glowRef.current.opacity = 0.14 + 0.06 * Math.sin(clock.elapsedTime * 1.4);
  });
  return (
    <group>
      {/* soft outer glow strand */}
      <mesh geometry={glowGeometry}>
        <meshBasicMaterial ref={glowRef} color={MODEL_COLORS.helios} transparent opacity={0.16} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      {/* bright core strand — the verified forecast */}
      <mesh geometry={geometry}>
        <meshBasicMaterial ref={matRef} color={MODEL_COLORS.heliosCore} transparent opacity={0.8} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh ref={pulseRef}>
        <sphereGeometry args={[0.045, 14, 14]} />
        <meshBasicMaterial color={MODEL_COLORS.heliosCore} transparent opacity={0.98} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
    </group>
  );
}

function Scene() {
  const group = useRef<THREE.Group>(null);
  // Extremely subtle drift so the composition feels alive without spinning.
  useFrame(({ clock, pointer }) => {
    if (!group.current) return;
    const targetY = pointer.x * 0.12;
    const targetX = -pointer.y * 0.08;
    group.current.rotation.y += (targetY - group.current.rotation.y) * 0.03;
    group.current.rotation.x += (targetX - group.current.rotation.x) * 0.03;
    group.current.position.y = Math.sin(clock.elapsedTime * 0.5) * 0.02;
  });
  return (
    <group ref={group}>
      <Stream from={[-1.7, 0.85, -0.2]} color={MODEL_COLORS.gfs} phase={0} />
      <Stream from={[-1.9, 0, 0.1]} color={MODEL_COLORS.ifs} phase={0.33} />
      <Stream from={[-1.7, -0.85, -0.2]} color={MODEL_COLORS.icon} phase={0.66} />
      <HeliosCore />
      <ForecastEmission />
    </group>
  );
}

/** Static, dependency-free SVG shown when animation is disabled. */
function StaticFallback() {
  return (
    <svg viewBox="0 0 400 300" className="h-full w-full" role="img" aria-label="GFS, IFS and ICON weather models converging into a single HELIOS forecast">
      <defs>
        <radialGradient id="hcore" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#fff2d6" />
          <stop offset="60%" stopColor="#ffc773" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#ffc773" stopOpacity="0" />
        </radialGradient>
      </defs>
      <path d="M40 70 Q140 110 195 150" stroke="#4da3ff" strokeWidth="2" fill="none" opacity="0.7" />
      <path d="M28 150 Q130 150 195 150" stroke="#8b7cff" strokeWidth="2" fill="none" opacity="0.7" />
      <path d="M40 230 Q140 190 195 150" stroke="#2fd6b4" strokeWidth="2" fill="none" opacity="0.7" />
      <path d="M205 150 Q300 158 372 165" stroke="#ffc773" strokeWidth="4" fill="none" opacity="0.9" />
      <path d="M205 150 Q300 158 372 165" stroke="#fff2d6" strokeWidth="1.5" fill="none" opacity="0.9" />
      <circle cx="200" cy="150" r="46" fill="url(#hcore)" />
      <circle cx="200" cy="150" r="9" fill="#fff2d6" />
      <circle cx="40" cy="70" r="3" fill="#4da3ff" />
      <circle cx="28" cy="150" r="3" fill="#8b7cff" />
      <circle cx="40" cy="230" r="3" fill="#2fd6b4" />
      <circle cx="372" cy="165" r="3.5" fill="#ffc773" />
    </svg>
  );
}

export function ModelConvergence({ className = "" }: { className?: string }) {
  const reduced = useReducedMotion();

  if (reduced) {
    return (
      <div className={className}>
        <StaticFallback />
      </div>
    );
  }

  return (
    <div className={className}>
      <Canvas
        camera={{ position: [0, 0, 4.2], fov: 42 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        style={{ background: "transparent" }}
      >
        <Scene />
      </Canvas>
    </div>
  );
}

export default ModelConvergence;
