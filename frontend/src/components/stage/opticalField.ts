/**
 * HELIOS OPTICAL FIELD — refraction without a container.
 *
 * The previous implementation used a bevelled rounded-box mesh, which read as an
 * empty rounded rectangle sitting behind the hero. That is a UI box, not a
 * material, so it is gone.
 *
 * This replaces it with an EDGELESS lens: a fullscreen pass whose refraction
 * strength is driven by a smooth radial mask plus a slow noise warp. Because the
 * mask never reaches a boundary, there is no silhouette to perceive — only a
 * region of the atmosphere that bends light. It gives the hero optical depth
 * while remaining part of the environment.
 *
 * Technique: the mask's analytic gradient is used as a surface normal, so the
 * scene texture is displaced radially (strongest in the falloff ring, zero at
 * the centre and at the outside) with a small per-channel split for dispersion.
 * One texture read in the flat regions, three in the ring.
 */

export const FIELD_LENS_VERT = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

export const FIELD_LENS_FRAG = /* glsl */ `
precision highp float;

varying vec2 vUv;

uniform sampler2D uScene;    // the atmosphere, already rendered
uniform vec2  uResolution;
uniform float uTime;
uniform vec2  uCenter;       // lens centre in 0..1
uniform float uRadius;       // falloff radius (screen units)
uniform float uStrength;     // refraction amount
uniform float uDispersion;
uniform float uPresence;     // 0 disables the whole pass

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x),
             mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}

void main() {
  vec2 uv = vUv;
  float aspect = uResolution.x / max(uResolution.y, 1.0);
  vec2 d2 = (uv - uCenter) * vec2(aspect, 1.0);
  float d = length(d2);

  // Smooth mask: 1 at the centre, 0 by uRadius. No edge anywhere.
  float mask = 1.0 - smoothstep(0.0, uRadius, d);
  // Breathe the lens very slowly so the medium is never static.
  float warp = noise(d2 * 2.2 + uTime * 0.03) - 0.5;
  mask = clamp(mask + warp * 0.10 * mask, 0.0, 1.0);
  mask *= uPresence;

  if (mask <= 0.002) {
    gl_FragColor = texture2D(uScene, uv);
    return;
  }

  // Refraction follows the mask's gradient: zero at the centre (looking straight
  // through) and zero outside, peaking in the falloff ring — exactly how a real
  // lens bends light.
  float ring = mask * (1.0 - mask) * 4.0;          // 0..1, peaks mid-falloff
  vec2 n = d2 / max(d, 1e-4);
  float amount = uStrength * ring;

  vec3 col;
  if (ring > 0.10) {
    float s = amount * uDispersion * 0.006;
    col.r = texture2D(uScene, uv - n * (amount + s)).r;
    col.g = texture2D(uScene, uv - n * amount).g;
    col.b = texture2D(uScene, uv - n * (amount - s)).b;
  } else {
    col = texture2D(uScene, uv - n * amount).rgb;
  }

  // A soft internal lift and a whisper of edge light in the ring: the sense of
  // volume, with no outline.
  col += col * mask * 0.10;
  col += ring * vec3(0.42, 0.55, 0.80) * 0.045;

  gl_FragColor = vec4(col, 1.0);
}
`;
