"use client";

import { Canvas, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useState } from "react";
import { HeliosRobot } from "./HeliosRobot";
import { createStudioEnvironment } from "./robotEnvironment";
import {
  usePointerTracker,
  useReducedMotion,
  type Anchor,
} from "./robotInteraction";

/**
 * Scene shell for the HELIOS robot: a stable cinematic camera, a dark studio
 * lighting rig and the interaction wiring.
 *
 * The camera never reacts to the pointer — only the robot does. That separation
 * is what makes the robot feel like it is paying attention to the visitor
 * instead of the whole world tilting.
 */

function detectWebGL(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    if (!gl) return false;
    (gl as WebGLRenderingContext).getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

/**
 * Generates the environment map and attaches it to the scene declaratively —
 * `attach="environment"` sets `scene.environment` and reverts it on unmount,
 * so no imperative mutation of the scene is required.
 */
function StudioEnvironment() {
  const gl = useThree((s) => s.gl);
  const texture = useMemo(() => createStudioEnvironment(gl), [gl]);

  useEffect(() => () => texture.dispose(), [texture]);

  return <primitive object={texture} attach="environment" />;
}

interface SceneContentsProps {
  anchor: Anchor;
  reducedMotion: boolean;
  interactive: boolean;
  interactionProgress: number;
  accent?: string;
}

function SceneContents({
  anchor,
  reducedMotion,
  interactive,
  interactionProgress,
  accent,
}: SceneContentsProps) {
  // The canvas element is the reference frame for pointer normalisation.
  const domElement = useThree((s) => s.gl.domElement);
  const pointer = usePointerTracker(domElement, anchor);

  return (
    <>
      <StudioEnvironment />

      {/* Dark studio: low ambient, cool key, cyan-tinted rim, gentle fill. */}
      <ambientLight intensity={0.16} color="#42536b" />
      <hemisphereLight args={["#5c7690", "#05070a", 0.22]} />
      <directionalLight position={[-3.2, 3.4, 3.6]} intensity={2.1} color="#e8f2ff" />
      <directionalLight position={[4.2, 2.2, -3]} intensity={1.5} color="#8fd8e8" />
      <directionalLight position={[-2.4, 0.4, 2.4]} intensity={0.32} color="#7f93ad" />
      <pointLight position={[0.5, 1.95, 1.15]} intensity={0.5} distance={3.4} color="#3fd8e8" />

      <HeliosRobot
        pointer={pointer}
        reducedMotion={reducedMotion}
        interactive={interactive}
        interactionProgress={interactionProgress}
        accent={accent}
      />
    </>
  );
}

export interface RobotSceneProps {
  className?: string;
  /**
   * Reserved hook for a future scroll-driven timeline (0…1). Mouse attention is
   * the primary interaction for now.
   */
  interactionProgress?: number;
  accent?: string;
}

export function RobotScene({ className, interactionProgress = 0, accent }: RobotSceneProps) {
  const reducedMotion = useReducedMotion();
  const [webgl, setWebgl] = useState<boolean | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setWebgl(detectWebGL()));
    return () => cancelAnimationFrame(id);
  }, []);

  // No WebGL (or a lost context): stay honest — a quiet vignette, never a fake
  // 2D stand-in for the 3D robot.
  if (webgl === false || failed) {
    return (
      <div
        aria-hidden
        className={className}
        style={{
          background:
            "radial-gradient(closest-side, rgba(63,216,232,0.07), rgba(5,7,10,0) 70%)",
        }}
      />
    );
  }

  if (webgl === null) return <div aria-hidden className={className} />;

  /**
   * Touch devices are handled by the pointer tracker itself: it only accepts
   * `mouse`/`pen` events, so on a touch-only device the rig never activates and
   * the robot holds its neutral pose. Deriving the fallback from observed input
   * is more reliable than a `pointer: fine` media query, which hybrid
   * touchscreen laptops (and some headless browsers) report incorrectly.
   */
  const interactive = !reducedMotion;

  return (
    <div
      className={className}
      // Decorative: the robot conveys no information a screen reader needs, and
      // it must never intercept clicks meant for the page beneath it.
      aria-hidden
      style={{ pointerEvents: "none" }}
    >
      <Canvas
        // Reduced motion renders a single static frame instead of a render loop.
        frameloop={reducedMotion ? "demand" : "always"}
        dpr={[1, 1.75]}
        camera={{ position: [0.85, 1.72, 4.5], fov: 31, near: 0.1, far: 40 }}
        gl={{
          antialias: true,
          alpha: true,
          powerPreference: "high-performance",
          failIfMajorPerformanceCaveat: false,
        }}
        style={{ width: "100%", height: "100%" }}
        onCreated={({ gl, camera }) => {
          camera.lookAt(0, 1.32, 0);
          gl.domElement.addEventListener(
            "webglcontextlost",
            (e) => {
              e.preventDefault();
              setFailed(true);
            },
            { once: true },
          );
        }}
      >
        <SceneContents
          anchor={{ x: 0, y: 0.15 }}
          reducedMotion={reducedMotion}
          interactive={interactive}
          interactionProgress={interactionProgress}
          accent={accent}
        />
      </Canvas>
    </div>
  );
}
