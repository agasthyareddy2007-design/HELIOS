"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Shared top navigation for the marketing surfaces (landing, contact) and the
 * route into the forecast instrument. Deliberately thin and quiet — it must not
 * compete with the cinematic hero.
 */

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/forecast", label: "Forecast" },
  { href: "/contact", label: "Contact" },
] as const;

export interface SiteNavProps {
  /** Transparent over a hero, or solid once the user scrolls / on inner pages. */
  variant?: "overlay" | "solid";
}

export function SiteNav({ variant = "overlay" }: SiteNavProps) {
  const pathname = usePathname();

  return (
    <header
      className={[
        "fixed inset-x-0 top-0 z-50",
        // A thin optical rail: the environment stays visible through it, so the
        // navigation belongs to the same material as the page behind it.
        "border-b border-[rgba(126,165,218,0.10)]",
        variant === "solid"
          ? "bg-[rgba(7,11,18,0.62)] backdrop-blur-[18px] backdrop-saturate-[1.3]"
          : "bg-[rgba(7,11,18,0.34)] backdrop-blur-[14px] backdrop-saturate-[1.25]",
      ].join(" ")}
    >
      <nav className="mx-auto flex max-w-[1500px] items-center justify-between px-6 py-3 md:px-10">
        <Link href="/" className="group inline-flex min-h-[44px] items-center gap-3 rounded-full pr-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]" aria-label="HELIOS — home">
          <span className="relative flex h-5 w-5 items-center justify-center">
            <span className="absolute inset-0 rounded-md border border-[var(--helios-amber)]/50 transition-colors group-hover:border-[var(--helios-amber)]" />
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--helios-amber)]" />
          </span>
          <span className="font-display text-[16px] font-semibold uppercase tracking-[0.30em] text-[var(--ink)]">
            Helios
          </span>
        </Link>

        <ul className="flex items-center gap-1 sm:gap-2">
          {LINKS.map((l) => {
            const active =
              l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <li key={l.href}>
                <Link
                  href={l.href}
                  aria-current={active ? "page" : undefined}
                  className={[
                    "relative inline-flex min-h-[44px] items-center rounded-full px-4 font-mono text-[12px] uppercase tracking-[0.14em] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]",
                    active
                      ? "text-[var(--helios-amber)]"
                      : "text-[var(--ink-dim)] hover:text-[var(--ink)]",
                  ].join(" ")}
                >
                  {l.label}
                  {active && (
                    <span className="absolute inset-x-4 bottom-[9px] h-px bg-[var(--helios-amber)]/70" />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
