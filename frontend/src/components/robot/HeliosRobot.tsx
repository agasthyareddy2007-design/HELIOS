"use client";

import { useFrame } from "@react-three/fiber";
import { createGestureRunner } from "./robotGesture";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import {
  collarGeometry,
  disposeAll,
  jointGeometry,
  limbGeometry,
  ringGeometry,
  shellGeometry,
} from "./robotGeometry";
import { createRobotMaterials, EMISSIVE, type RobotMaterials } from "./robotMaterials";
import { clamp, damp, degToRad, RIG, type PointerState } from "./robotInteraction";

/**
 * HELIOS ROBOT — original procedural humanoid, built from chamfered Three.js
 * shells (no external model asset, no drei).
 *
 * The rig is two nested pivots: the torso answers the pointer weakly (it reads
 * as mass) and the head, parented to it, answers strongly. Because the head is
 * a child of the torso its motion is additive, which is why the two need very
 * different easing rates — the head leads and the body trails.
 */

/** Rig proportions in world units; the robot stands ~2.45 units tall. */
const P = {
  footY: 0.07,
  ankleY: 0.2,
  shinLen: 0.5,
  kneeY: 0.72,
  thighLen: 0.52,
  hipY: 1.18,
  legX: 0.19,

  waistY: 1.18,
  chestY: 0.4,
  chestW: 0.78,
  chestH: 0.66,
  chestD: 0.42,

  shoulderY: 0.6,
  shoulderX: 0.46,
  upperArmLen: 0.48,
  lowerArmLen: 0.44,

  neckY: 0.78,
  headPivotY: 0.86,
  headY: 0.22,
} as const;

interface GeometrySet {
  chest: THREE.ExtrudeGeometry;
  chestPanel: THREE.ExtrudeGeometry;
  abdomen: THREE.ExtrudeGeometry;
  hip: THREE.ExtrudeGeometry;
  head: THREE.ExtrudeGeometry;
  visor: THREE.ExtrudeGeometry;
  sensorBar: THREE.ExtrudeGeometry;
  earPod: THREE.ExtrudeGeometry;
  hand: THREE.ExtrudeGeometry;
  foot: THREE.ExtrudeGeometry;
  neck: THREE.CylinderGeometry;
  collar: THREE.CylinderGeometry;
  upperArm: THREE.CapsuleGeometry;
  lowerArm: THREE.CapsuleGeometry;
  thigh: THREE.CapsuleGeometry;
  shin: THREE.CapsuleGeometry;
  shoulderBall: THREE.SphereGeometry;
  elbow: THREE.SphereGeometry;
  knee: THREE.SphereGeometry;
  coreRing: THREE.TorusGeometry;
  coreDisc: THREE.SphereGeometry;
  all: THREE.BufferGeometry[];
}

function createGeometry(): GeometrySet {
  const g = {
    chest: shellGeometry(P.chestW, P.chestH, P.chestD, { radius: 0.15, bevel: 0.035 }),
    chestPanel: shellGeometry(0.44, 0.3, 0.06, { radius: 0.09, bevel: 0.016 }),
    abdomen: shellGeometry(0.52, 0.24, 0.34, { radius: 0.1, bevel: 0.028 }),
    hip: shellGeometry(0.62, 0.22, 0.38, { radius: 0.1, bevel: 0.03 }),
    head: shellGeometry(0.46, 0.42, 0.4, { radius: 0.16, bevel: 0.04 }),
    visor: shellGeometry(0.38, 0.26, 0.05, { radius: 0.11, bevel: 0.014 }),
    sensorBar: shellGeometry(0.24, 0.032, 0.02, { radius: 0.014, bevel: 0.006 }),
    earPod: shellGeometry(0.07, 0.16, 0.12, { radius: 0.032, bevel: 0.012 }),
    hand: shellGeometry(0.11, 0.16, 0.09, { radius: 0.04, bevel: 0.014 }),
    foot: shellGeometry(0.19, 0.11, 0.34, { radius: 0.045, bevel: 0.018 }),
    neck: collarGeometry(0.085, 0.12, 14),
    collar: collarGeometry(0.055, 0.05, 12),
    upperArm: limbGeometry(0.072, P.upperArmLen),
    lowerArm: limbGeometry(0.062, P.lowerArmLen),
    thigh: limbGeometry(0.1, P.thighLen),
    shin: limbGeometry(0.082, P.shinLen),
    shoulderBall: jointGeometry(0.115),
    elbow: jointGeometry(0.07, 14),
    knee: jointGeometry(0.095, 14),
    coreRing: ringGeometry(0.075, 0.014),
    coreDisc: jointGeometry(0.05, 14),
  };
  return { ...g, all: Object.values(g) };
}

interface LimbProps {
  side: 1 | -1;
  g: GeometrySet;
  m: RobotMaterials;
}

/**
 * Shoulder → upper arm → elbow → lower arm → wrist → hand.
 * The group is exposed via `groupRef` so the shoulder can be driven by the
 * occasional greeting gesture; at rest it holds the neutral pose.
 */
function Arm({
  side,
  g,
  m,
  groupRef,
}: LimbProps & { groupRef?: React.Ref<THREE.Group> }) {
  const x = side * P.shoulderX;
  return (
    <group ref={groupRef} position={[x, P.shoulderY, 0]} rotation={[0, 0, side * -0.06]}>
      <mesh geometry={g.shoulderBall} material={m.joint} />
      <mesh geometry={g.upperArm} material={m.shell} position={[0, -P.upperArmLen / 2 - 0.06, 0]} />
      <mesh geometry={g.elbow} material={m.joint} position={[0, -P.upperArmLen - 0.08, 0]} />
      <mesh
        geometry={g.lowerArm}
        material={m.panel}
        position={[0, -P.upperArmLen - P.lowerArmLen / 2 - 0.12, 0]}
      />
      <mesh
        geometry={g.collar}
        material={m.trim}
        position={[0, -P.upperArmLen - P.lowerArmLen - 0.16, 0]}
      />
      <mesh
        geometry={g.hand}
        material={m.shell}
        position={[0, -P.upperArmLen - P.lowerArmLen - 0.27, 0.01]}
      />
    </group>
  );
}

/** Hip → thigh → knee → shin → ankle → foot. */
function Leg({ side, g, m }: LimbProps) {
  const x = side * P.legX;
  return (
    <group position={[x, 0, 0]}>
      <mesh geometry={g.thigh} material={m.shell} position={[0, P.hipY - P.thighLen / 2 - 0.08, 0]} />
      <mesh geometry={g.knee} material={m.joint} position={[0, P.kneeY, 0]} />
      <mesh geometry={g.shin} material={m.panel} position={[0, P.kneeY - P.shinLen / 2 - 0.06, 0]} />
      <mesh geometry={g.collar} material={m.trim} position={[0, P.ankleY, 0]} />
      <mesh geometry={g.foot} material={m.shell} position={[0, P.footY, 0.07]} />
    </group>
  );
}

export interface HeliosRobotProps {
  /** Live pointer state; mutated outside React and read once per frame. */
  pointer: React.RefObject<PointerState>;
  /** Freeze continuous motion and hold a neutral pose. */
  reducedMotion?: boolean;
  /** False on touch-only devices → static, attentive idle pose. */
  interactive?: boolean;
  /**
   * Reserved for a future scroll-driven timeline (0…1). Currently applies only
   * a slight forward attention lean so the API can be wired without a rewrite.
   */
  interactionProgress?: number;
  accent?: string;
}

export function HeliosRobot({
  pointer,
  reducedMotion = false,
  interactive = true,
  interactionProgress = 0,
  accent,
}: HeliosRobotProps) {
  const headRef = useRef<THREE.Group>(null);
  const torsoRef = useRef<THREE.Group>(null);

  const g = useMemo(() => createGeometry(), []);
  const m = useMemo(() => createRobotMaterials({ accent }), [accent]);

  useEffect(() => () => disposeAll([...g.all, ...m.all]), [g, m]);

  /**
   * The two emissive materials are held in refs so the render loop mutates a ref
   * rather than a value created during render (per-frame material mutation is
   * idiomatic react-three-fiber, but it must not touch render-scoped values).
   */
  const sensorMat = useRef<THREE.MeshStandardMaterial | null>(null);
  const coreMat = useRef<THREE.MeshStandardMaterial | null>(null);
  useEffect(() => {
    sensorMat.current = m.sensor;
    coreMat.current = m.core;
  }, [m]);

  /** Eased rig state — never React state, so no renders happen while animating. */
  const rig = useRef({ headYaw: 0, headPitch: 0, torsoYaw: 0, torsoPitch: 0, glow: 0, t: 0 });

  /** Right shoulder, driven only by the occasional greeting. */
  const rightArmRef = useRef<THREE.Group>(null);
  // Created lazily on the first frame: `performance.now()` must not be read
  // during render (React purity), and the frame loop is the natural owner.
  const gesture = useRef<ReturnType<typeof createGestureRunner> | null>(null);
  const armRest = -0.06; // neutral shoulder angle for side = +1

  useFrame((_, delta) => {
    // Cap dt so a background tab returning to focus cannot jolt the rig.
    const dt = Math.min(delta, 0.05);
    const r = rig.current;
    r.t += dt;

    const p = pointer.current;
    const lean = clamp(interactionProgress, 0, 1);

    let targetHeadYaw = 0;
    let targetHeadPitch = 0;
    let targetTorsoYaw = 0;
    let targetTorsoPitch = 0;
    let targetGlow = 0;

    if (interactive && !reducedMotion && p?.active) {
      // Idle relax: once the pointer has been still, the attention target decays
      // back to neutral instead of holding a stare indefinitely.
      const still = performance.now() - p.lastMoveAt > RIG.idleRelaxMs;
      const hold = still ? Math.exp(-RIG.relaxLambda * dt * 60) : 1;

      const x = clamp(p.x, -1, 1);
      const y = clamp(p.y, -1, 1);

      targetHeadYaw = degToRad(RIG.headYawDeg) * x * hold;
      // Screen-up is +y; looking up is a negative rotation about X.
      targetHeadPitch = -degToRad(RIG.headPitchDeg) * y * hold;
      targetTorsoYaw = degToRad(RIG.torsoYawDeg) * x * hold;
      targetTorsoPitch = -degToRad(RIG.torsoPitchDeg) * y * hold;

      // Proximity: nearer pointer → marginally brighter instrumentation.
      targetGlow = 1 - p.distance;
    }

    r.headYaw = damp(r.headYaw, targetHeadYaw, RIG.headLambda, dt);
    r.headPitch = damp(r.headPitch, targetHeadPitch, RIG.headLambda, dt);
    r.torsoYaw = damp(r.torsoYaw, targetTorsoYaw, RIG.torsoLambda, dt);
    r.torsoPitch = damp(r.torsoPitch, targetTorsoPitch, RIG.torsoLambda, dt);
    r.glow = damp(r.glow, targetGlow, RIG.glowLambda, dt);

    // Mechanical micro-motion: sub-degree, so it reads as servo hold rather than
    // a floating idle loop. Disabled entirely under reduced motion.
    const micro = reducedMotion || !interactive ? 0 : Math.sin(r.t * 0.55) * 0.0022;

    if (headRef.current) {
      headRef.current.rotation.y = r.headYaw + micro;
      headRef.current.rotation.x = r.headPitch + micro * 0.5 - lean * 0.05;
    }
    if (torsoRef.current) {
      torsoRef.current.rotation.y = r.torsoYaw;
      torsoRef.current.rotation.x = r.torsoPitch + lean * 0.03;
    }

    // ---- occasional greeting -------------------------------------------
    // Fires only when a visitor is present and the pointer is in a lull, so it
    // reads as the robot noticing someone rather than performing on a timer.
    const arm = rightArmRef.current;
    if (arm) {
      const now = performance.now();
      if (gesture.current === null) gesture.current = createGestureRunner(now);
      const gs = gesture.current.update(
        now,
        p.active,
        now - p.lastMoveAt,
        !reducedMotion && interactive,
      );
      if (gs.raise > 0.0005) {
        // Raise up-and-out, then a slow wave from the shoulder.
        const raised = armRest + gs.raise * (2.02 - armRest);
        arm.rotation.z = raised + gs.wave * 0.19;
        arm.rotation.x = -gs.raise * 0.16;
      } else if (arm.rotation.z !== armRest) {
        arm.rotation.z = armRest;
        arm.rotation.x = 0;
      }
    }

    const attention = clamp(r.glow + lean * 0.35, 0, 1);
    const sensor = sensorMat.current;
    const core = coreMat.current;
    if (sensor) {
      sensor.emissiveIntensity =
        EMISSIVE.sensorBase + (EMISSIVE.sensorPeak - EMISSIVE.sensorBase) * attention;
    }
    if (core) {
      core.emissiveIntensity =
        EMISSIVE.coreBase + (EMISSIVE.corePeak - EMISSIVE.coreBase) * attention;
    }
  });

  return (
    // Slight three-quarter stance: a dead-on front view flattens the shells.
    <group rotation={[0, -0.22, 0]}>
      {/* legs + feet: structural, never follow the pointer */}
      <Leg side={-1} g={g} m={m} />
      <Leg side={1} g={g} m={m} />
      <mesh geometry={g.hip} material={m.shell} position={[0, P.hipY + 0.02, 0]} />

      {/* torso pivot at the waist — small, slow response */}
      <group ref={torsoRef} position={[0, P.waistY, 0]}>
        <mesh geometry={g.abdomen} material={m.joint} position={[0, 0.16, 0]} />
        <mesh geometry={g.chest} material={m.shell} position={[0, P.chestY, 0]} />
        <mesh geometry={g.chestPanel} material={m.panel} position={[0, P.chestY + 0.06, P.chestD / 2]} />
        <mesh geometry={g.coreRing} material={m.trim} position={[0, P.chestY - 0.09, P.chestD / 2 + 0.02]} />
        <mesh geometry={g.coreDisc} material={m.core} position={[0, P.chestY - 0.09, P.chestD / 2 + 0.02]} />

        <Arm side={-1} g={g} m={m} />
        <Arm side={1} g={g} m={m} groupRef={rightArmRef} />

        <mesh geometry={g.neck} material={m.joint} position={[0, P.neckY, 0]} />

        {/* head pivot at the top of the neck — primary responder */}
        <group ref={headRef} position={[0, P.headPivotY, 0]}>
          <mesh geometry={g.head} material={m.shell} position={[0, P.headY, 0]} />
          {/* black reflective display, inset slightly into the shell */}
          <mesh geometry={g.visor} material={m.face} position={[0, P.headY + 0.01, 0.185]} />
          <mesh geometry={g.sensorBar} material={m.sensor} position={[0, P.headY + 0.03, 0.212]} />
          <mesh geometry={g.earPod} material={m.panel} position={[-0.235, P.headY, 0]} />
          <mesh geometry={g.earPod} material={m.panel} position={[0.235, P.headY, 0]} />
        </group>
      </group>
    </group>
  );
}
