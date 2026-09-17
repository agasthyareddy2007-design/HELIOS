import * as THREE from "three";

/**
 * Geometry factories for the HELIOS robot.
 *
 * @react-three/drei is not a project dependency, so the rounded/chamfered
 * hardware look is built from Three.js primitives directly. Extruding a
 * rounded profile with a bevel produces genuine chamfered edges, which is what
 * separates a machined-looking shell from an obvious box.
 */

/** Rounded rectangle profile centred on the origin. */
function roundedRect(w: number, h: number, r: number): THREE.Shape {
  const radius = Math.min(r, Math.min(w, h) / 2 - 1e-4);
  const x = -w / 2;
  const y = -h / 2;
  const s = new THREE.Shape();
  s.moveTo(x + radius, y);
  s.lineTo(x + w - radius, y);
  s.absarc(x + w - radius, y + radius, radius, -Math.PI / 2, 0, false);
  s.lineTo(x + w, y + h - radius);
  s.absarc(x + w - radius, y + h - radius, radius, 0, Math.PI / 2, false);
  s.lineTo(x + radius, y + h);
  s.absarc(x + radius, y + h - radius, radius, Math.PI / 2, Math.PI, false);
  s.lineTo(x, y + radius);
  s.absarc(x + radius, y + radius, radius, Math.PI, Math.PI * 1.5, false);
  return s;
}

export interface ShellOptions {
  /** Corner radius of the extruded profile. */
  radius?: number;
  /** Chamfer size on the extruded faces. */
  bevel?: number;
  /** Profile smoothness; keep low — these are small on-screen objects. */
  curveSegments?: number;
  bevelSegments?: number;
}

/**
 * A rounded, chamfered slab centred on the origin, extruded along +Z then
 * centred. Used for every hard shell panel (torso, limbs, feet, head).
 */
export function shellGeometry(
  width: number,
  height: number,
  depth: number,
  { radius = 0.06, bevel, curveSegments = 6, bevelSegments = 2 }: ShellOptions = {},
): THREE.ExtrudeGeometry {
  const b = Math.min(bevel ?? Math.min(width, height, depth) * 0.09, depth / 2 - 1e-3);
  const geo = new THREE.ExtrudeGeometry(roundedRect(width, height, radius), {
    depth: Math.max(depth - b * 2, 1e-3),
    bevelEnabled: b > 0,
    bevelThickness: b,
    bevelSize: b,
    bevelOffset: 0,
    bevelSegments,
    curveSegments,
  });
  geo.center();
  geo.computeVertexNormals();
  return geo;
}

/** Capsule limb segment (upper/lower arms and legs). */
export function limbGeometry(radius: number, length: number, radial = 14): THREE.CapsuleGeometry {
  return new THREE.CapsuleGeometry(radius, Math.max(length - radius * 2, 1e-3), 4, radial);
}

/** Spherical joint / shoulder ball. */
export function jointGeometry(radius: number, segments = 16): THREE.SphereGeometry {
  return new THREE.SphereGeometry(radius, segments, Math.max(8, segments / 2));
}

/** Cylindrical hardware: neck column, wrist collars, hip axle. */
export function collarGeometry(
  radius: number,
  height: number,
  radial = 16,
): THREE.CylinderGeometry {
  return new THREE.CylinderGeometry(radius, radius, height, radial, 1, false);
}

/** Thin ring used for restrained accent hardware. */
export function ringGeometry(radius: number, tube: number): THREE.TorusGeometry {
  return new THREE.TorusGeometry(radius, tube, 8, 28);
}

/** Dispose every geometry/material we created explicitly on unmount. */
export function disposeAll(
  items: Array<THREE.BufferGeometry | THREE.Material | null | undefined>,
): void {
  for (const item of items) item?.dispose();
}
