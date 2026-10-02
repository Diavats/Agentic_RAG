"use client";
// How it works: Prismo walks through one real question, step by step.
// As each step scrolls into view, the star chart beside it replays that step.

import { useEffect, useRef, useState } from "react";
import StarChart from "@/components/StarChart";
import data from "@/lib/sample-trace.json";

const t = data.trace;
const v = t.verification;
const sec = (ms: number) => `${(ms / 1000).toFixed(1)}s`;

// The five steps, written from the recorded run (no made-up numbers).
const STEPS = [
  {
    title: "Pick the topic",
    body: `Your question sits much closer to the medical files (${t.routing.scores.medical.toFixed(2)}) than to finance (${t.routing.scores.financial.toFixed(2)}), so I only search medical. Deciding took ${sec(t.routing.latency_ms)} and no AI call: it's a similarity score.`,
  },
  {
    title: "Plan the search",
    body: t.planning.subqueries.length > 1
      ? `Your question asks ${t.planning.subqueries.length} things, so I split it: ${t.planning.subqueries.map((s) => `"${s}"`).join(" and ")}.`
      : "Your question asks one thing, so I run one search.",
  },
  {
    title: "Find the passages",
    body: `For each search I look two ways at once: by meaning, and by exact keywords. Then I merge both rankings, so passages that do well in both rise to the top. I kept the best ${t.retrieval.sources.length}; a bigger star ranked higher.`,
  },
  {
    title: "Write the answer",
    body: `I answer only from those passages and cite each one I use. The pink lines join the answer to the ${t.synthesis.citations.length} passages it cited.`,
  },
  {
    title: "Check my work",
    body: v
      ? `A model from a different AI company checks every claim against the passages. Here ${v.supported_claims} of ${v.total_claims} claims were supported (${Math.round(v.score * 100)}%). I show this even when it's low.`
      : "A second model checks each claim against the passages.",
  },
];

// Things PRISM is honestly bad at, or doesn't do.
const LIMITS = [
  ["\"Which is the highest?\" questions", "I find the closest passages, not every row, so I can miss the true top value."],
  ["Small test set", "Each topic was tested on 11 answerable questions, so one question moves a score by about 0.09."],
  ["Only finance and medical", "Files on other topics are refused before any upload is used."],
  ["Spreadsheets up to 25 rows", "Each row costs one AI call, and the daily budget is shared."],
  ["Uploads are temporary", "Your files disappear after an hour, or when the free server goes to sleep."],
  ["Not advice", "Answers are for exploring documents, not for medical or financial decisions."],
];

export default function HowItWorks() {
  const [step, setStep] = useState(0);
  const refs = useRef<(HTMLElement | null)[]>([]); // the five step headings

  // Whichever step card is in the middle of the screen becomes the active step.
  useEffect(() => {
    const seen = new IntersectionObserver(
      (items) => items.forEach((it) => it.isIntersecting && setStep(Number((it.target as HTMLElement).dataset.stepHeading))),
      // On phones the chart covers the top half, so the band that activates a
      // step sits just below it: a step turns on only when its title is in view.
      { rootMargin: window.matchMedia("(max-width: 767px)").matches ? "-52% 0px -33% 0px" : "-40% 0px -50% 0px" },
    );
    refs.current.forEach((el) => el && seen.observe(el));
    return () => seen.disconnect();
  }, []);

  return (
    <main className="mx-auto max-w-6xl px-4 pb-24 pt-10">
      <h1 className="text-[clamp(44px,7vw,84px)]">How I find an answer</h1>
      <p className="mt-4 max-w-[60ch] text-xl font-semibold">
        Scroll to replay one real question:{" "}
        <span className="sticker inline-block bg-card px-2">&ldquo;{t.question}&rdquo;</span>
      </p>
      <p className="mt-2 text-sm font-semibold">
        Recorded from the live system on {new Date(data.recorded_at).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}.
        Every number below comes from that run.
      </p>

      <div className="mt-12 grid gap-10 md:grid-cols-[1fr_1.1fr]">
        {/* The story, one card per step. */}
        <ol className="flex flex-col gap-[38vh] pb-[30vh] pt-[8vh]">
          {STEPS.map((s, i) => (
            <li
              key={s.title}
              data-step={i + 1}
              className={`card p-5 transition-[transform,background-color] duration-300 ${step === i + 1 ? "bg-sun" : "bg-card"}`}
              style={{ transform: step === i + 1 ? "rotate(-1deg)" : "none" }}
            >
              <h2
                ref={(el) => { refs.current[i] = el; }}
                data-step-heading={i + 1}
                className="flex items-center gap-3 text-3xl"
              >
                {/* The same numbered slot the chat uses for this step. */}
                <span className="sticker shrink-0 bg-card px-2 py-0.5 text-lg tabular-nums" aria-label={`Step ${i + 1} of 5:`}>
                  {String(i + 1).padStart(2, "0")}
                </span>
                {s.title}
              </h2>
              <p className="mt-3">{s.body}</p>
            </li>
          ))}
        </ol>

        {/* The chart stays on screen while the story scrolls past. */}
        <div className="md:sticky md:top-28 md:h-fit max-md:sticky max-md:top-[118px] max-md:z-10 max-md:-mx-4 max-md:order-first max-md:border-b-[3px] max-md:border-ink max-md:bg-gum max-md:px-[max(16px,calc(50%-120px))] max-md:pb-2">
          <StarChart step={step} />
          <p className="mt-3 text-sm font-bold max-md:mt-1 max-md:text-xs">
            Lilac: medical passages. Mint: finance. Pink: your question and what it cited.
          </p>
        </div>
      </div>

      {/* Honest limits. */}
      <section className="mt-10">
        <h2 className="text-4xl">What I can't do (yet)</h2>
        <ul className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {LIMITS.map(([title, body], i) => (
            <li key={title} className="sticker bg-card p-4" style={{ transform: `rotate(${i % 2 ? 1 : -1}deg)` }}>
              <h3 className="text-xl">{title}</h3>
              <p className="mt-1 text-[15px]">{body}</p>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
