"use client";
// The top bar: PRISM logo, the four page tabs, and two live badges:
// is the server awake, and how many questions you have left today.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { health, quota, type Quota } from "@/lib/api";

const TABS = [
  { href: "/", label: "Welcome" },
  { href: "/chat", label: "Chat" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/benchmarks", label: "Benchmarks" },
];

export default function Nav() {
  const path = usePathname();
  const [status, setStatus] = useState<"waking" | "ready" | "offline">("waking");
  const [left, setLeft] = useState<Quota | null>(null);

  // Ping the server until it answers. The free server sleeps and takes ~1 min to wake.
  useEffect(() => {
    let stop = false;
    const started = Date.now();
    async function ping() {
      try {
        await health();
        if (stop) return;
        setStatus("ready");
        setLeft(await quota());
      } catch {
        if (stop) return;
        if (Date.now() - started > 150_000) setStatus("offline"); // gave up after 2.5 min
        else setTimeout(ping, 5000);
      }
    }
    ping();
    // Other components announce "quota changed" after asking or uploading.
    const refresh = () => quota().then(setLeft).catch(() => {});
    window.addEventListener("prism:quota", refresh);
    return () => { stop = true; window.removeEventListener("prism:quota", refresh); };
  }, []);

  const pill = {
    waking: { text: "Waking up the server…", bg: "var(--baby)" },
    ready: { text: "Ready", bg: "var(--mint)" },
    offline: { text: "Server is offline", bg: "var(--card)" },
  }[status];

  return (
    <header className="sticky top-0 z-30 border-b-[3px] border-ink bg-gum/90 backdrop-blur-sm">
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
        {/* Logo sticker. */}
        <Link href="/" className="sticker bg-hot px-3 py-1 text-xl font-extrabold" style={{ transform: "rotate(-3deg)" }}>
          PRISM
        </Link>

        {/* Page tabs. They scroll sideways on small phones. */}
        <div className="no-scrollbar flex min-w-0 flex-1 gap-2 overflow-x-auto px-1 py-2">
          {TABS.map((t) => {
            const on = t.href === "/" ? path === "/" : path.startsWith(t.href);
            return (
              <Link
                key={t.href}
                href={t.href}
                aria-current={on ? "page" : undefined}
                className={`lift sticker shrink-0 px-3 py-1 text-sm font-bold ${on ? "bg-sun" : "bg-card"}`}
              >
                {t.label}
              </Link>
            );
          })}
        </div>

        {/* Server status + questions left today. */}
        <div className="flex shrink-0 items-center gap-2 text-xs font-bold max-sm:w-full sm:text-sm" aria-live="polite">
          <span className="sticker px-2 py-0.5" style={{ background: pill.bg }}>{pill.text}</span>
          {left && (
            <span className={`sticker px-2 py-0.5 ${left.question.left <= 3 ? "bg-sun" : "bg-card"}`}>
              {left.question.left} of {left.question.limit} questions left today
            </span>
          )}
        </div>
      </nav>
    </header>
  );
}
