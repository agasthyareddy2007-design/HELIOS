"use client";

import { useEffect, useSyncExternalStore } from "react";
import { SiteNav } from "@/components/site/SiteNav";
import { RobotScene } from "@/components/robot";
import { Button } from "@/components/ui/Button";
import { useStage } from "@/components/stage/useStage";

/**
 * /contact — TWO SUBJECTS, ONE SCENE.
 *
 * Hard art direction: the page is the team's message and the HELIOS robot, side
 * by side, held together by the atmosphere. Nothing else competes with them —
 * no glass panels, no card surfaces, no contact form, no decorative slabs. The
 * type sits directly in the environment; the robot is the other half of the
 * composition, not an illustration beside a form.
 *
 * The robot itself is already an interactive entity (it tracks the pointer,
 * breathes, and relaxes when the pointer leaves — see components/robot). This
 * page's job is only to give it space and light.
 */

/** Render exactly one robot canvas: CSS visibility would still mount two. */
function useWide(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia("(min-width: 1024px)");
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => window.matchMedia("(min-width: 1024px)").matches,
    () => true,
  );
}

export default function ContactPage() {
  const wide = useWide();

  // The robot is this page's subject: the environment recedes behind it.
  useEffect(() => {
    useStage.getState().setMode("subject");
    return () => useStage.getState().setMode("cinematic");
  }, []);

  return (
    <>
      <SiteNav variant="overlay" />

      <main className="relative text-[var(--color-ink)]">
        <section
          className="relative mx-auto flex min-h-[100svh] max-w-[1200px] flex-col px-6 pb-14 pt-28 md:px-10 lg:pt-24"
          aria-label="Project and contact"
        >
          <div className="grid flex-1 items-center gap-10 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] lg:gap-16">
            {/* ---------------- SUBJECT ONE — the team's message ---------------- */}
            <div className="relative z-[1] max-w-[40ch]">
              <p className="t-meta">Project &amp; contact</p>

              <h1 className="t-display mt-6 text-[clamp(3rem,6.2vw,5.2rem)]">
                Built to be
                <span className="block text-[var(--helios-amber)]">questioned.</span>
              </h1>

              <p className="mt-8 text-[19px] leading-[1.62] text-[var(--ink-dim)]">
                HELIOS is a learned weather-model arbitration layer built for SIH26081.
                It only earns trust through scrutiny — of the method, the verification
                and the numbers.
              </p>
              <p className="mt-5 text-[17px] leading-[1.68] text-[var(--ink-faint)]">
                Questions, critique and collaboration are all welcome. The fastest way
                to judge it is to watch it forecast.
              </p>

              <div className="mt-10 flex flex-wrap gap-3">
                <Button href="/forecast" variant="primary" size="lg" trailing="→">
                  See it forecasting
                </Button>
                <Button href="/" variant="ghost" size="lg">
                  How it works
                </Button>
              </div>
            </div>

            {/* ---------------- SUBJECT TWO — the HELIOS entity ----------------- */}
            {/* No frame, no panel: the robot stands in the atmosphere itself. */}
            {wide ? (
              <div className="robot-stage relative h-[74vh] min-h-[520px] w-full">
                <RobotScene className="h-full w-full" />
              </div>
            ) : (
              <div className="robot-stage relative h-[52vh] min-h-[340px] w-full">
                <RobotScene className="h-full w-full" />
              </div>
            )}
          </div>

          {/* One quiet line of plain type — no surface, no panel. */}
          <div className="relative z-[1] mt-10 flex flex-wrap items-center gap-x-10 gap-y-3 border-t border-[rgba(126,165,218,0.10)] pt-6">
            <span className="t-meta">SIH26081 · HELIOS</span>
            <span className="text-[14px] text-[var(--ink-faint)]">
              Weather-model arbitration &amp; verification
            </span>
            <span className="flex items-center gap-4">
              {[
                { n: "GFS", c: "var(--color-gfs)" },
                { n: "IFS", c: "var(--color-ifs)" },
                { n: "ICON", c: "var(--color-icon)" },
              ].map((m) => (
                <span key={m.n} className="inline-flex items-center gap-2">
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ background: m.c, boxShadow: `0 0 9px ${m.c}` }}
                  />
                  <span
                    className="font-mono text-[13px] tracking-[0.08em]"
                    style={{ color: m.c }}
                  >
                    {m.n}
                  </span>
                </span>
              ))}
            </span>
          </div>
        </section>
      </main>
    </>
  );
}
