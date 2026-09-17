/**
 * HELIOS ATMOSPHERE FIELD — the medium the optical glass refracts.
 *
 * A restrained, slow-moving atmospheric volume rather than a "shader demo":
 * domain-warped fbm gives structure, the HELIOS spectral hues (GFS blue,
 * IFS violet, ICON teal) resolve toward HELIOS amber along a large-scale
 * convergence axis, and a fine grain breaks up banding. It reacts to real
 * HELIOS state — model disagreement raises turbulence, the most-trusted model
 * tints the field — so the environment is a readout, not decoration.
 */

export const FIELD_VERT = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

export const FIELD_FRAG = /* glsl */ `
precision highp float;

varying vec2 vUv;

uniform float uTime;
uniform vec2  uResolution;
uniform float uTurbulence;   // 0..1 — driven by model disagreement
uniform vec3  uTrustTint;    // blend of the model colours by trust weight
uniform float uScroll;       // 0..1 page scroll — the field evolves as you descend
uniform float uQuality;      // 1 = desktop, 0 = reduced (fewer octaves)
uniform float uPresence;     // 1 = cinematic routes, <1 = instrument routes
uniform vec2  uPointer;      // smoothed pointer in 0..1 screen space
uniform float uEnergy;       // 0..1 pointer activity — the field responds to presence
uniform vec3  uFocusColor;   // spectral hue of the attended signal
uniform float uFocus;        // 0..1 how strongly that signal has taken over
uniform float uResolve;      // 0..1 section progress: divergence -> resolution

const vec3 GFS   = vec3(0.302, 0.639, 1.000);
const vec3 IFS   = vec3(0.545, 0.486, 1.000);
const vec3 ICON  = vec3(0.184, 0.839, 0.706);
const vec3 AMBER = vec3(1.000, 0.780, 0.451);
const vec3 VOID  = vec3(0.016, 0.027, 0.047);

vec2 hash2(vec2 p) {
  p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
  return -1.0 + 2.0 * fract(sin(p) * 43758.5453);
}

float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(dot(hash2(i + vec2(0, 0)), f - vec2(0, 0)),
                 dot(hash2(i + vec2(1, 0)), f - vec2(1, 0)), u.x),
             mix(dot(hash2(i + vec2(0, 1)), f - vec2(0, 1)),
                 dot(hash2(i + vec2(1, 1)), f - vec2(1, 1)), u.x), u.y);
}

float fbm(vec2 p, int octaves) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 5; i++) {
    if (i >= octaves) break;
    v += a * noise(p);
    p *= 2.02;
    a *= 0.5;
  }
  return v;
}

/** Cheap hash for film grain. */
float grain(vec2 p) {
  return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void main() {
  vec2 uv = vUv;
  float aspect = uResolution.x / max(uResolution.y, 1.0);
  vec2 p = (uv - 0.5) * vec2(aspect, 1.0) * 2.2;

  int octaves = uQuality > 0.5 ? 4 : 3;
  float t = uTime * 0.018;                       // deliberately slow: atmosphere, not fluid
  float turb = 0.6 + uTurbulence * 0.9;

  // Presence: the medium is displaced very slightly toward the pointer, more so
  // while the pointer is moving. This is what makes the environment feel aware
  // rather than decorative — it is a field reacting to a body in it.
  vec2 toP = uv - uPointer;
  float pd = length(toP * vec2(aspect, 1.0));
  float near = exp(-pd * pd * 5.5);               // smooth locality, no hard edge
  p -= normalize(toP + 1e-5) * near * (0.10 + 0.22 * uEnergy);

  // domain warp — two levels, enough for believable atmospheric structure
  vec2 q = vec2(fbm(p + vec2(0.0, t), octaves),
                fbm(p + vec2(4.7, -t), octaves));
  vec2 r = vec2(fbm(p + turb * q + vec2(1.7, 9.2) + 0.12 * t, octaves),
                fbm(p + turb * q + vec2(8.3, 2.8) - 0.10 * t, octaves));
  float f = fbm(p + 2.2 * r, octaves);

  // Convergence axis: cool model signals on one side resolving into HELIOS
  // amber on the other — the site's core idea expressed as light.
  float axis = 0.5 + 0.5 * sin((uv.x * 1.1 + uv.y * 0.75) * 3.14159
                               + f * 1.8 + uScroll * 2.6);

  vec3 cool = mix(GFS, ICON, smoothstep(0.15, 0.9, q.y + 0.35 * r.x));
  cool = mix(cool, IFS, smoothstep(0.2, 0.85, r.x));
  vec3 warm = mix(IFS, AMBER, smoothstep(0.25, 0.95, f + 0.45 * r.y));

  // The narrative state biases the whole field: early sections read cool and
  // divergent, later sections resolve warm. This is the story told as light.
  float bias = smoothstep(0.2, 0.8, axis + (uResolve - 0.5) * 0.55);
  vec3 col = mix(cool, warm, bias);

  // Attention: when the visitor focuses one model, that spectral identity takes
  // over the field and the other signals recede. The environment is showing what
  // it is "thinking about".
  if (uFocus > 0.001) {
    float band = 0.55 + 0.45 * sin((uv.y * 3.0 - uv.x * 1.2) * 3.14159 + f * 3.2 + t * 1.4);
    vec3 focused = mix(col, uFocusColor, 0.75);
    focused += uFocusColor * band * 0.30;
    col = mix(col, focused, uFocus);
  }

  // trust tint: the dominant model very subtly colours the field
  col = mix(col, uTrustTint, 0.12);

  // Structure: atmospheric density from the warp.
  float density = smoothstep(-0.10, 0.92, f + 0.26 * axis);

  // a single warm ridge where the warp folds — the "resolved signal"
  float ridge = smoothstep(0.74, 1.0, f * 1.05 + 0.35 * axis);
  col = mix(col, mix(AMBER, vec3(1.0, 0.70, 0.48), 0.4), ridge * 0.38);

  // Composition: the left half carries headline + body copy on every route, so
  // the field stays deliberately quiet there and only opens up in empty space.
  float calm = smoothstep(0.30, 0.92, uv.x);
  float bloom = mix(0.18, 1.35, calm);

  // single radial falloff from the light centre
  float vig = smoothstep(1.5, 0.2, length((uv - vec2(0.72, 0.42)) * vec2(1.2, 1.0)));

  // light gathers where attention is
  col += col * near * (0.30 + 0.55 * uEnergy + 0.35 * uFocus);

  col *= density * bloom * (0.22 + 0.80 * vig);

  // Global restraint: the environment is a presence, never the subject.
  col *= 0.62 * uPresence;

  // fine grain — breaks banding, adds a filmic quality at almost no cost
  col += (grain(uv * uResolution.xy * 0.5) - 0.5) * 0.014;

  // lift off pure black so the material always has presence
  col += VOID * 1.35;
  gl_FragColor = vec4(col, 1.0);
}
`;
