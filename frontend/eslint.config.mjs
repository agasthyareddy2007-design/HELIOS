import coreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

/**
 * HELIOS frontend lint configuration (ESLint flat config).
 * Uses the native flat configs shipped by eslint-config-next 16.
 */
const eslintConfig = [
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      ".vercel/**",
      "next-env.d.ts",
    ],
  },
  ...coreWebVitals,
  ...nextTypescript,
  {
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      // react-three-fiber declares three.js properties as JSX props.
      "react/no-unknown-property": "off",
    },
  },
  {
    // ---------------------------------------------------------------------
    // WebGL layer exception — deliberate and narrowly scoped.
    //
    // `react-hooks/immutability` models values as frozen after render. GPU
    // uniform objects are, by design, MUTABLE handles into an external system
    // (the GPU), and react-three-fiber's `useFrame` is a render-loop
    // subscription that executes OUTSIDE React's render phase — it is the
    // documented "synchronise with an external system" case.
    //
    // Writing `uniform.value` / animation refs inside `useFrame` is the correct
    // and only performant pattern: the alternative (routing per-frame values
    // through React state) would trigger a re-render every frame at 60–120 Hz.
    //
    // The rule is disabled ONLY for this directory. All other React rules stay
    // enabled here, and the rest of the application remains fully strict.
    // ---------------------------------------------------------------------
    files: ["src/components/gl/**/*.tsx", "src/components/background/**/*.tsx"],
    rules: {
      "react-hooks/immutability": "off",
      "react-hooks/refs": "off",
    },
  },
];

export default eslintConfig;
