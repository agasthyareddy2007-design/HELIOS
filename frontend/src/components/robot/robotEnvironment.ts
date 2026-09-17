import * as THREE from "three";

/**
 * Procedural dark-studio environment.
 *
 * Physically-based metal is defined almost entirely by what it reflects, so a
 * metalness ~0.9 body lit only by direct lights renders as a black silhouette.
 * Rather than ship an HDRI, a few emissive quads are pre-filtered with
 * PMREMGenerator into an environment map — enough to give the shells specular
 * shape and the visor a believable reflection, at negligible cost (generated
 * once, on mount).
 */

interface Lightformer {
  color: THREE.ColorRepresentation;
  intensity: number;
  position: [number, number, number];
  scale: [number, number];
}

const STUDIO: Lightformer[] = [
  // broad soft key, upper front-left
  { color: "#cfe2ff", intensity: 2.6, position: [-3, 3, 3.5], scale: [7, 5] },
  // tight rim behind-right — this is what separates the body from the background
  { color: "#dbeeff", intensity: 3.4, position: [4, 2.4, -3.2], scale: [3.5, 6] },
  // low fill so the underside is not pure black
  { color: "#20303f", intensity: 1.1, position: [0, -2.6, 2.2], scale: [6, 3] },
  // restrained cyan accent, camera-left
  { color: "#3fd8e8", intensity: 1.15, position: [-2.6, 1.2, -2.2], scale: [2.4, 3] },
];

export function createStudioEnvironment(renderer: THREE.WebGLRenderer): THREE.Texture {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#05070a");

  const plane = new THREE.PlaneGeometry(1, 1);
  const materials: THREE.Material[] = [];

  for (const lf of STUDIO) {
    const material = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide });
    material.color.set(lf.color).multiplyScalar(lf.intensity);
    materials.push(material);

    const mesh = new THREE.Mesh(plane, material);
    mesh.position.set(...lf.position);
    mesh.scale.set(lf.scale[0], lf.scale[1], 1);
    mesh.lookAt(0, 0, 0);
    scene.add(mesh);
  }

  const pmrem = new THREE.PMREMGenerator(renderer);
  const texture = pmrem.fromScene(scene, 0.04).texture;

  pmrem.dispose();
  plane.dispose();
  for (const m of materials) m.dispose();
  scene.clear();

  return texture;
}
