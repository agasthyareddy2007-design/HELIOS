import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { HeliosStage } from "@/components/stage/HeliosStage";
import { CursorLight } from "@/components/stage/CursorLight";
import { RouteState } from "@/components/stage/RouteState";
import { AttentionReflector } from "@/components/stage/StateRegion";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

// Display voice: technical, engineered, strong at large sizes.
const grotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-grotesk",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "HELIOS — learned weather-model arbitration",
  description:
    "HELIOS does not learn the weather. It learns the conditional reliability of numerical weather models — predicting how much to trust GFS, IFS and ICON for a given place, hour and forecast horizon.",
  applicationName: "HELIOS",
  keywords: [
    "weather model blending",
    "NWP post-processing",
    "forecast arbitration",
    "model reliability",
    "GFS",
    "IFS",
    "ICON",
  ],
  authors: [{ name: "HELIOS" }],
  openGraph: {
    title: "HELIOS — learned weather-model arbitration",
    description:
      "A live weather-model arbitration layer that learns how much to trust GFS, IFS and ICON for a given place and forecast horizon.",
    type: "website",
  },
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: "#04070c",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable} ${grotesk.variable}`}>
      <body className="antialiased">
        {/* One shared optical environment behind every route. */}
        <HeliosStage />
        <CursorLight />
        <AttentionReflector />
        <RouteState>{children}</RouteState>
      </body>
    </html>
  );
}
