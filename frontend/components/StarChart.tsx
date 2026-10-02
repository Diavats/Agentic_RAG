"use client";
// The Star Atlas: every piece of PRISM's library is a star.
// Lilac stars are medical, mint stars are finance. As you scroll the story,
// the chart replays ONE real recorded question, step by step, and Prismo flies along.

import Prismo from "./Prismo";
import data from "@/lib/sample-trace.json";

const { trace, corpus } = data;

// Medical stars cluster on the left, finance stars on the right.
// Each cluster is a golden-angle spiral (like sunflower seeds): evenly spread,
// and the same every time, so server and browser draw identical charts.
const CENTRE = { medical: { x: 120, y: 225 }, financial: { x: 300, y: 235 } } as const;
const GOLDEN_ANGLE = 2.39996;
const stars = corpus.map((u) => {
  const same = corpus.filter((v) => v.domain === u.domain);
  const i = same.indexOf(u);
  const c = CENTRE[u.domain as keyof typeof CENTRE];
  const dist = 14 + 78 * Math.sqrt((i + 0.5) / same.length);
  return { ...u, x: c.x + Math.cos(i * GOLDEN_ANGLE) * dist, y: c.y + Math.sin(i * GOLDEN_ANGLE) * dist };
});

// The retrieved passages, their rank, and which ones the answer cited.
const found = new Map(trace.retrieval.sources.map((s) => [s.id, s]));
const scores = trace.retrieval.sources.map((s) => s.score);
const [lo, hi] = [Math.min(...scores), Math.max(...scores)];
const citedIds = new Set(
  trace.synthesis.citations.filter((c) => c.resolved).map((c) => c.source_id),
);

export default function StarChart({ step }: { step: number }) {
  // step: 0 = before start, 1 route, 2 plan, 3 retrieve, 4 answer, 5 verify
  const q = { x: 210, y: 360 };                   // where the question starts
  const target = step >= 1 ? CENTRE.medical : q;  // routing sends it to medical
  const split = step >= 2 && trace.planning.subqueries.length > 1;

  // Where Prismo hovers for each step of the story.
  const prismoAt = [
    { x: 250, y: 330 }, { x: 150, y: 70 }, { x: 40, y: 250 },
    { x: 200, y: 60 }, { x: 40, y: 80 }, { x: 160, y: 250 },
  ][step];

  return (
    <figure
      className="card relative overflow-hidden bg-ink p-0"
      aria-label="Star chart of PRISM's library"
      style={{ containerType: "inline-size" }} /* lets Prismo's position scale with the chart */
    >
      <svg viewBox="0 0 420 420" className="block w-full">
        {/* Faint chart grid. */}
        <defs>
          <pattern id="grid" width="42" height="42" patternUnits="userSpaceOnUse">
            <path d="M42 0H0V42" fill="none" stroke="#333" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="420" height="420" fill="url(#grid)" />

        {/* Cluster labels. */}
        <text x="70" y="62" fill="var(--lilac)" fontWeight="800" fontSize="15" opacity={step === 1 || step === 0 ? 1 : 0.6}>
          Medical {step >= 1 ? trace.routing.scores.medical.toFixed(2) : ""}
        </text>
        <text x="270" y="62" fill="var(--mint)" fontWeight="800" fontSize="15">
          Finance {step >= 1 ? trace.routing.scores.financial.toFixed(2) : ""}
        </text>

        {/* Constellation lines: from the question to every cited passage (step 4+). */}
        {stars.filter((s) => citedIds.has(s.id)).map((s) => (
          <line
            key={`l-${s.id}`}
            x1={target.x} y1={target.y} x2={s.x} y2={s.y}
            stroke="var(--hot)" strokeWidth="3"
            pathLength={1} strokeDasharray="1" strokeDashoffset={step >= 4 ? 0 : 1}
            style={{ transition: "stroke-dashoffset 700ms cubic-bezier(0.77,0,0.175,1)" }}
          />
        ))}

        {/* Every passage in the library is a star. */}
        {stars.map((s) => {
          const hit = found.get(s.id);
          // From step 3, a found passage grows with its rank among the 8 found.
          const grow = step >= 3 && hit ? 1.6 + ((hit.score - lo) / (hi - lo || 1)) * 1.6 : 1;
          const dim = step >= 1 && s.domain === "financial";
          return (
            <g key={s.id} transform={`translate(${s.x} ${s.y})`} opacity={dim ? 0.55 : 1} style={{ transition: "opacity 400ms ease" }}>
              <circle
                r="5"
                fill={step >= 4 && citedIds.has(s.id) ? "var(--hot)" : s.domain === "medical" ? "var(--lilac)" : "var(--mint)"}
                stroke="#fff"
                strokeWidth="1.5"
                style={{ transform: `scale(${grow})`, transformBox: "fill-box", transformOrigin: "center", transition: "transform 600ms cubic-bezier(0.77,0,0.175,1), fill 300ms ease" }}
              />
              {/* A tick on each cited passage once the answer is checked. */}
              {step >= 5 && citedIds.has(s.id) && (
                <path d="M8 -12 l4 4 l8 -9" fill="none" stroke="var(--sun)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              )}
            </g>
          );
        })}

        {/* The question: one pink star that travels, then splits into sub-searches. */}
        {(split ? [-18, 18] : [0]).map((dx, i) => (
          <circle
            key={i}
            r="9"
            fill="var(--hot)"
            stroke="#fff"
            strokeWidth="2.5"
            style={{
              transform: `translate(${target.x + dx}px, ${target.y + (split ? 26 : 0)}px)`,
              transition: "transform 700ms cubic-bezier(0.77,0,0.175,1)",
            }}
          />
        ))}
      </svg>

      {/* Prismo flies to where the action is. */}
      <div
        className="pointer-events-none absolute left-0 top-0"
        style={{
          transform: `translate(${(prismoAt.x / 420) * 100}cqw, ${(prismoAt.y / 420) * 100}cqw)`,
          transition: "transform 800ms cubic-bezier(0.77,0,0.175,1)",
        }}
      >
        <Prismo mood={step === 5 ? "happy" : step >= 2 && step <= 4 ? "thinking" : "idle"} size={64} />
      </div>
    </figure>
  );
}
