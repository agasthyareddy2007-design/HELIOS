import * as THREE from "three";

/**
 * Material set for the HELIOS robot — dark graphite hardware with restrained
 * cyan instrumentation.
 *
 * Roughness is deliberately varied between shells, panels and joints: a single
 * uniform metal reads as plastic, whereas differing microsurface response is
 * what makes separate parts look assembled rather than moulded as one piece.
 *
 * The emissive materials are returned by reference so the render loop can ease
 * `emissiveIntensity` (pointer proximity) without rebuilding materials.
 */

export interface RobotMaterials {
  /** Primary body shells. */
  shell: THREE.MeshStandardMaterial;
  /** Secondary panels — matte, slightly lighter, breaks up the silhouette. */
  panel: THREE.MeshStandardMaterial;
  /** Recessed joints and structural gaps — near black, low reflection. */
  joint: THREE.MeshStandardMaterial;
  /** Polished machined trim (collars, rings). */
  trim: THREE.MeshStandardMaterial;
  /** Black reflective face display. */
  face: THREE.MeshPhysicalMaterial;
  /** Cyan sensor bar / eye line. */
  sensor: THREE.MeshStandardMaterial;
  /** Cyan chest core. */
  core: THREE.MeshStandardMaterial;
  all: Array<THREE.Material>;
}

export interface MaterialOptions {
  /** Accent colour for instrumentation. Defaults to a restrained cyan. */
  accent?: THREE.ColorRepresentation;
}

export function createRobotMaterials({ accent = "#3fd8e8" }: MaterialOptions = {}): RobotMaterials {
  const accentColor = new THREE.Color(accent);

  const shell = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#171a1f"),
    metalness: 0.92,
    roughness: 0.34,
    envMapIntensity: 0.9,
  });

  const panel = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#1d222a"),
    metalness: 0.68,
    roughness: 0.62,
    envMapIntensity: 0.6,
  });

  const joint = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#080a0d"),
    metalness: 0.55,
    roughness: 0.78,
  });

  const trim = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#9aa6b4"),
    metalness: 1,
    roughness: 0.18,
    envMapIntensity: 1.1,
  });

  // Piano-black visor: clearcoat over a near-black base gives a wet, reflective
  // display read without needing an environment map or postprocessing.
  const face = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color("#04060a"),
    metalness: 0.25,
    roughness: 0.06,
    clearcoat: 1,
    clearcoatRoughness: 0.04,
    reflectivity: 0.85,
  });

  const sensor = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#0d1418"),
    emissive: accentColor.clone(),
    emissiveIntensity: 1.15,
    metalness: 0.3,
    roughness: 0.4,
    toneMapped: false,
  });

  const core = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#0b1216"),
    emissive: accentColor.clone(),
    emissiveIntensity: 0.55,
    metalness: 0.4,
    roughness: 0.45,
    toneMapped: false,
  });

  return {
    shell,
    panel,
    joint,
    trim,
    face,
    sensor,
    core,
    all: [shell, panel, joint, trim, face, sensor, core],
  };
}

/** Baseline emissive levels; proximity eases between base and base * peak. */
export const EMISSIVE = {
  sensorBase: 1.15,
  sensorPeak: 2.15,
  coreBase: 0.55,
  corePeak: 0.95,
} as const;
