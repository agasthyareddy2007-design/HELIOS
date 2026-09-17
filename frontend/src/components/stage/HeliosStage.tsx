"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { FIELD_FRAG, FIELD_VERT } from "./fieldShaders";
import { FIELD_LENS_FRAG, FIELD_LENS_VERT } from "./opticalField";
import { useStage } from "./useStage";

/**
 * HELIOS STAGE — one shared optical environment for the entire site.
 *
 * Architecture (chosen after comparing DOM-rasterising liquid-glass libraries
 * against in-scene WebGL refraction):
 *
 *   ONE WebGL context, mounted once in the root layout as a fixed backdrop:
 *
 *     AtmosphereField   fullscreen procedural HELIOS atmosphere (the medium)
 *     OpticalGlass      bevelled slabs that hide themselves, capture the live
 *                       scene into an FBO, then refract it with per-channel IOR
 *                       dispersion + Fresnel + Blinn-Phong specular
 *
 *   All typography and controls stay in the DOM above the canvas, so text is
 *   crisp, selectable and accessible while the environment behind it is a real
 *   optical material.
 *
 * Why not a DOM liquid-glass library: those rasterise HTML (SVG
 * feDisplacementMap / backdrop-filter / html2canvas) and therefore cannot
 * refract a live WebGL scene — and the Chromium-only `backdrop-filter: url()`
 * variants degrade to a flat blur elsewhere. Refracting in-scene gives true
 * live refraction, one context, and no page-sized textures.
 *
 * Performance: DPR capped at 2, dispersion loop fixed at 6 samples, half-res
 * FBO, quality tiers by viewport, `frameloop` paused when the tab is hidden,
 * every geometry/material/target explicitly disposed.
 */

/** Spectral identity per attended signal, including the resolved HELIOS state. */
const STAGE_FOCUS_COLORS: Record<string, THREE.Color> = {
  // Level 1 — NWP model inputs
  gfs: new THREE.Color("#4da3ff"),
  ifs: new THREE.Color("#8b7cff"),
  icon: new THREE.Color("#2fd6b4"),
  // Level 2 — blending candidates
  kernel: new THREE.Color("#e07a9a"),
  xgboost: new THREE.Color("#f0a55e"),
  mlp: new THREE.Color("#ffc773"),
  // the resolved output
  helios: new THREE.Color("#ffc773"),
};

const MODEL_COLORS = {
  gfs: new THREE.Color("#4da3ff"),
  ifs: new THREE.Color("#8b7cff"),
  icon: new THREE.Color("#2fd6b4"),
};

function useMedia(query: string, fallback = false): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia(query);
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => window.matchMedia(query).matches,
    () => fallback,
  );
}

function detectWebGL(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl2") ?? c.getContext("webgl");
    if (!gl) return false;
    (gl as WebGLRenderingContext).getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

/* ------------------------------------------------------------------ scene */

function StageScene({ tier }: { tier: "full" | "reduced" | "static" }) {
  const { gl, scene, size, viewport } = useThree();
  const store = useRef<{
    field: THREE.ShaderMaterial;
    fieldScene: THREE.Scene;
    fieldMesh: THREE.Mesh;
    geos: THREE.BufferGeometry[];
    lensMat: THREE.ShaderMaterial;
    fbo: THREE.WebGLRenderTarget;
    cam: THREE.Camera;
    trust: THREE.Color;
    ptr: { x: number; y: number };
    energy: number;
    focusAmt: number;
    resolveAmt: number;
  } | null>(null);

  useEffect(() => {
    // The field is expensive (multi-octave fbm), so it is evaluated ONCE per
    // frame into an offscreen target. The on-screen pass then reads that texture
    // through an edgeless optical lens — one fbm evaluation, no container mesh.
    const fieldScene = new THREE.Scene();
    const fieldGeo = new THREE.PlaneGeometry(2, 2);
    const field = new THREE.ShaderMaterial({
      vertexShader: FIELD_VERT,
      fragmentShader: FIELD_FRAG,
      depthWrite: false,
      depthTest: false,
      uniforms: {
        uTime: { value: 0 },
        uResolution: { value: new THREE.Vector2(1, 1) },
        uTurbulence: { value: 0.25 },
        uTrustTint: { value: new THREE.Color("#4da3ff") },
        uScroll: { value: 0 },
        uQuality: { value: tier === "full" ? 1 : 0 },
        uPresence: { value: 1 },
        uPointer: { value: new THREE.Vector2(0.5, 0.5) },
        uEnergy: { value: 0 },
        uFocusColor: { value: new THREE.Color("#4da3ff") },
        uFocus: { value: 0 },
        uResolve: { value: 0 },
      },
    });
    const fieldQuad = new THREE.Mesh(fieldGeo, field);
    fieldQuad.frustumCulled = false;
    fieldScene.add(fieldQuad);

    const fbo = new THREE.WebGLRenderTarget(1, 1, {
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      depthBuffer: false,
    });

    // The on-screen pass IS the optical field: it samples the atmosphere and
    // bends it through an edgeless lens. No container mesh, no silhouette.
    const blitGeo = new THREE.PlaneGeometry(2, 2);
    const lensMat = new THREE.ShaderMaterial({
      depthWrite: false,
      depthTest: false,
      uniforms: {
        uScene: { value: fbo.texture },
        uResolution: { value: new THREE.Vector2(1, 1) },
        uTime: { value: 0 },
        uCenter: { value: new THREE.Vector2(0.62, 0.46) },
        uRadius: { value: 0.72 },
        uStrength: { value: 0.05 },
        uDispersion: { value: 1.0 },
        uPresence: { value: 1 },
      },
      vertexShader: FIELD_LENS_VERT,
      fragmentShader: FIELD_LENS_FRAG,
    });
    const fieldMesh = new THREE.Mesh(blitGeo, lensMat);
    fieldMesh.frustumCulled = false;
    fieldMesh.renderOrder = -10;
    scene.add(fieldMesh);

    store.current = {
      field,
      fieldScene,
      fieldMesh,
      lensMat,
      geos: [fieldGeo, blitGeo],
      fbo,
      cam: new THREE.Camera(),
      trust: new THREE.Color("#4da3ff"),
      ptr: { x: 0.5, y: 0.5 },
      energy: 0,
      focusAmt: 0,
      resolveAmt: 0.12,
    };

    return () => {
      const s = store.current;
      if (!s) return;
      scene.remove(s.fieldMesh);
      s.fieldScene.clear();
      s.geos.forEach((g) => g.dispose());
      s.field.dispose();
      s.lensMat.dispose();
      s.fbo.dispose();
      store.current = null;
    };
  }, [scene, tier]);

  useFrame((state) => {
    const s = store.current;
    if (!s) return;

    const live = useStage.getState();
    const dpr = Math.min(1.5, viewport.dpr || 1);
    const bw = Math.max(1, Math.floor(size.width * dpr));
    const bh = Math.max(1, Math.floor(size.height * dpr));

    // Reduced-resolution FBO with an ABSOLUTE cap. The field is soft and gets
    // refracted, so resolution is cheap to trade away — and capping by pixel
    // budget (rather than a pure ratio) stops a 4K display from costing 4x a
    // 1080p one. Bounded textures, independent of monitor size.
    const ratio = tier === "full" ? 0.5 : 0.4;
    const MAX_W = tier === "full" ? 960 : 640;
    const scale = Math.min(ratio, MAX_W / Math.max(1, bw));
    const fw = Math.max(1, Math.floor(bw * scale));
    const fh = Math.max(1, Math.floor(bh * scale));
    if (s.fbo.width !== fw || s.fbo.height !== fh) s.fbo.setSize(fw, fh);

    const t = tier === "reduced" ? 12.0 : state.clock.elapsedTime;

    // Pointer presence, smoothed. r3f gives NDC (-1..1, y up); the shader wants
    // 0..1 with y down. Energy decays, so the field settles when the user stops.
    const pu = s.ptr;
    const nx = (state.pointer.x + 1) * 0.5;
    const ny = 1 - (state.pointer.y + 1) * 0.5;
    const dx = nx - pu.x, dy = ny - pu.y;
    const moved = Math.min(1, Math.hypot(dx, dy) * 9);
    pu.x += dx * 0.09;
    pu.y += dy * 0.09;
    s.energy += (moved - s.energy) * (moved > s.energy ? 0.22 : 0.035);
    (s.field.uniforms.uPointer!.value as THREE.Vector2).set(pu.x, pu.y);
    s.field.uniforms.uEnergy!.value = tier === "reduced" ? 0 : s.energy;
    const instrument = live.mode === "instrument";
    const subject = live.mode === "subject";
    // Quiet the field and retire the slabs on the instrument route so dense
    // data always reads first. Eased, so route changes feel like the material
    // settling rather than a hard switch.
    const targetPresence = instrument ? 0.42 : subject ? 0.6 : 1.0;
    const pres = s.field.uniforms.uPresence!;
    pres.value += (targetPresence - (pres.value as number)) * 0.06;

    // ---- field uniforms (live HELIOS state drives the atmosphere) ----
    s.field.uniforms.uTime!.value = t;
    (s.field.uniforms.uResolution!.value as THREE.Vector2).set(bw, bh);
    s.field.uniforms.uTurbulence!.value = live.turbulence;
    s.field.uniforms.uScroll!.value = live.scroll;

    // ---- attention + narrative state ----------------------------------
    const FOCUS_COLORS: Record<string, THREE.Color> = STAGE_FOCUS_COLORS;
    const wantFocus = live.focus ? 1 : 0;
    s.focusAmt += (wantFocus - s.focusAmt) * 0.07;
    s.field.uniforms.uFocus!.value = tier === "reduced" ? 0 : s.focusAmt;
    if (live.focus) {
      const target = FOCUS_COLORS[live.focus];
      if (target) (s.field.uniforms.uFocusColor!.value as THREE.Color).lerp(target, 0.10);
    }

    const SECTION_RESOLVE: Record<string, number> = {
      arrival: 0.12,
      divergence: 0.22,
      signals: 0.38,
      reasoning: 0.55,
      verification: 0.74,
      resolution: 1.0,
    };
    const wantResolve = SECTION_RESOLVE[live.section] ?? 0.2;
    s.resolveAmt += (wantResolve - s.resolveAmt) * 0.035;
    s.field.uniforms.uResolve!.value = s.resolveAmt;

    if (live.weights) {
      const { gfs, ifs, icon } = live.weights;
      const total = Math.max(1e-4, gfs + ifs + icon);
      const wg = gfs / total, wi = ifs / total, wc = icon / total;
      s.trust.setRGB(
        MODEL_COLORS.gfs.r * wg + MODEL_COLORS.ifs.r * wi + MODEL_COLORS.icon.r * wc,
        MODEL_COLORS.gfs.g * wg + MODEL_COLORS.ifs.g * wi + MODEL_COLORS.icon.g * wc,
        MODEL_COLORS.gfs.b * wg + MODEL_COLORS.ifs.b * wi + MODEL_COLORS.icon.b * wc,
      );
      (s.field.uniforms.uTrustTint!.value as THREE.Color).lerp(s.trust, 0.05);
    }

    // ---- optical field ----
    // The lens has no silhouette, so instead of "moving an object" we simply
    // let the region of bent light drift toward where the user is looking.
    const lu = s.lensMat.uniforms;
    (lu.uResolution!.value as THREE.Vector2).set(bw, bh);
    lu.uTime!.value = t;
    const lc = lu.uCenter!.value as THREE.Vector2;
    if (tier === "full" && !instrument) {
      lc.x += (0.5 + (pu.x - 0.5) * 0.55 - lc.x) * 0.02;
      lc.y += (0.46 + (pu.y - 0.5) * 0.40 - lc.y) * 0.02;
    }
    // Depth belongs to the cinematic hero; the instrument gets none, and the
    // subject route only a trace.
    const lensTarget = instrument ? 0.0 : subject ? 0.35 : 1.0;
    lu.uPresence!.value += (lensTarget - (lu.uPresence!.value as number)) * 0.05;
    lu.uStrength!.value = 0.05 + 0.02 * s.energy;

    // ---- one field evaluation per frame, into the FBO ----
    // The on-screen optical field samples this texture, so the costly fbm shader
    // runs exactly once per frame.
    gl.setRenderTarget(s.fbo);
    gl.render(s.fieldScene, s.cam);
    gl.setRenderTarget(null);
  });

  return null;
}

/* ------------------------------------------------------------------ shell */

/** Probe once per page load and cache, so getSnapshot stays referentially stable. */
let webglCache: boolean | null = null;
function webglSupported(): boolean {
  if (webglCache === null) webglCache = detectWebGL();
  return webglCache;
}
const noopSubscribe = () => () => {};

export function HeliosStage() {
  const reduced = useMedia("(prefers-reduced-motion: reduce)");
  const mobile = useMedia("(max-width: 820px)");
  // null on the server (renders the CSS field), resolved boolean on the client.
  const webgl = useSyncExternalStore<boolean | null>(
    noopSubscribe,
    webglSupported,
    () => null,
  );

  // Publish scroll progress into the stage store (rAF-throttled, no React state).
  useEffect(() => {
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const max = document.documentElement.scrollHeight - window.innerHeight;
        useStage.getState().setScroll(max > 0 ? window.scrollY / max : 0);
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  // No WebGL, or reduced motion on a small device → CSS field only.
  if (webgl === false) {
    return <div aria-hidden className="helios-field-css pointer-events-none fixed inset-0 -z-10" />;
  }
  if (webgl === null) {
    return <div aria-hidden className="helios-field-css pointer-events-none fixed inset-0 -z-10" />;
  }

  const tier: "full" | "reduced" | "static" = reduced ? "reduced" : mobile ? "reduced" : "full";

  // The backdrop is soft and refracted, so resolution buys nothing above a
  // point. Large viewports already have many fragments — drop DPR there.
  const wide = typeof window !== "undefined" && window.innerWidth >= 1700;
  const maxDpr = wide ? 1 : 1.5;

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10">
      <div className="helios-field-css absolute inset-0" />
      <Canvas
        className="absolute inset-0"
        camera={{ position: [0, 0, 5.2], fov: 45 }}
        dpr={[1, maxDpr]}
        frameloop={reduced ? "demand" : "always"}
        gl={{ antialias: !mobile, alpha: true, powerPreference: "high-performance" }}
        style={{ background: "transparent" }}
        onCreated={({ gl }) => {
          gl.domElement.setAttribute("aria-hidden", "true");
          gl.setClearColor(0x000000, 0);
        }}
      >
        <StageScene tier={tier} />
      </Canvas>
    </div>
  );
}

export default HeliosStage;
