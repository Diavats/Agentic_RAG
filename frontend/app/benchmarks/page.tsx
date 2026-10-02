"use client";
// Benchmarks: the real evaluation numbers, read live from GET /benchmark.
// Bad numbers stay in. Each section says in plain words what it means.

import { useEffect, useState } from "react";
import Prismo from "@/components/Prismo";
import { benchmark } from "@/lib/api";

type Arm = { "recall@5": number; mrr: number; n: number };
type Bench = {
  generated_at: string;
  models: { generator: string; judge: string; embeddings: string };
  retrieval_ablation: Record<string, Record<"dense" | "sparse" | "hybrid", Arm>>;
  router_ablation: Record<string, { accuracy: number; correct: number; n: number }>;
  pipeline_ablation?: Record<string, Record<"naive" | "agentic", { "recall@5": number; citation_accuracy: number; abstention_rate: number }>>;
};

const TOPIC: Record<string, string> = { financial: "Finance", medical: "Medical" };
const METHOD = { dense: "By meaning", sparse: "By keywords", hybrid: "Both, merged" } as const;
const COLOUR = { dense: "bg-lilac", sparse: "bg-baby", hybrid: "bg-hot" } as const;

// One horizontal bar: label, a sticker-bar sized to the value, the value itself.
function Bar({ label, value, colour, grown }: { label: string; value: number; colour: string; grown: boolean }) {
  return (
    <div className="grid grid-cols-[110px_1fr_52px] items-center gap-3 text-sm font-bold">
      <span>{label}</span>
      <div className="h-7 rounded-md border-[3px] border-ink bg-card">
        <div
          className={`h-full ${colour} border-r-[3px] border-ink`}
          style={{ width: `${value * 100}%`, transform: `scaleX(${grown ? 1 : 0.02})`, transformOrigin: "left", transition: "transform 700ms cubic-bezier(0.23,1,0.32,1)" }}
        />
      </div>
      <span className="tabular-nums">{value.toFixed(3)}</span>
    </div>
  );
}

export default function Benchmarks() {
  const [b, setB] = useState<Bench | null>(null);
  const [err, setErr] = useState("");
  const [grown, setGrown] = useState(false);

  // Fetch once; bars grow in the frame after the numbers arrive.
  useEffect(() => {
    benchmark()
      .then((data) => { setB(data as Bench); requestAnimationFrame(() => setGrown(true)); })
      .catch(() => setErr("The server is waking up or offline. Try again in a minute."));
  }, []);

  if (!b) {
    return (
      <main className="mx-auto flex max-w-3xl flex-col items-center gap-4 px-4 py-24 text-center">
        <Prismo mood={err ? "sorry" : "thinking"} size={120} />
        <p className="text-xl font-bold">{err || "Fetching the latest results…"}</p>
      </main>
    );
  }

  const router = Object.values(b.router_ablation)[0];
  // Sentences below are computed from the numbers, so they can't go stale.
  const arms = Object.values(b.retrieval_ablation);
  const hybridRanksBest = arms.every((a) => a.hybrid.mrr >= Math.max(a.dense.mrr, a.sparse.mrr));
  const hybridFindsMost = arms.every((a) => a.hybrid["recall@5"] >= Math.max(a.dense["recall@5"], a.sparse["recall@5"]));
  const splitMatters = b.pipeline_ablation && Object.values(b.pipeline_ablation).some((a) => a.naive["recall@5"] !== a.agentic["recall@5"]);

  return (
    <main className="mx-auto max-w-6xl px-4 pb-24 pt-10">
      <h1 className="text-[clamp(44px,7vw,84px)]">How well it works</h1>
      <p className="mt-4 max-w-[62ch] text-xl font-semibold">
        Measured on a fixed set of test questions with known correct passages. Every number is shown as measured, including where my design choices didn't help.
      </p>

      {/* 1. Which search method finds the right passage. */}
      <section className="mt-14">
        <h2 className="text-4xl">Finding the right passage</h2>
        <p className="mt-2 max-w-[62ch]">
          <b>Found it</b> (recall): how often the right passage was in the top 5. <b>Ranked it high</b> (MRR): how close to first place it came. 1.000 is perfect.
        </p>
        <div className="mt-6 grid gap-6 md:grid-cols-2">
          {Object.entries(b.retrieval_ablation).map(([topic, arms]) => (
            <div key={topic} className="card bg-card p-5">
              <h3 className="text-2xl">{TOPIC[topic] ?? topic} <span className="text-base font-semibold">({arms.hybrid.n} questions)</span></h3>
              <p className="mt-4 font-extrabold">Found it</p>
              <div className="mt-2 space-y-2">
                {(Object.keys(METHOD) as (keyof typeof METHOD)[]).map((m) => (
                  <Bar key={m} label={METHOD[m]} value={arms[m]["recall@5"]} colour={COLOUR[m]} grown={grown} />
                ))}
              </div>
              <p className="mt-5 font-extrabold">Ranked it high</p>
              <div className="mt-2 space-y-2">
                {(Object.keys(METHOD) as (keyof typeof METHOD)[]).map((m) => (
                  <Bar key={m} label={METHOD[m]} value={arms[m].mrr} colour={COLOUR[m]} grown={grown} />
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="sticker mt-6 max-w-[70ch] bg-sun p-4" style={{ transform: "rotate(-0.5deg)" }}>
          <b>The honest read:</b> merging both searches {hybridRanksBest ? "ranks the right passage highest in every topic" : "does not always rank best"}
          {hybridFindsMost ? ", and finds the most too." : ", but it doesn't always find the most."} With 11 questions per topic, one question changes recall by about 0.09, so small gaps here are within noise.
        </div>
      </section>

      {/* 2. Picking the topic: the result sits inside the sentence that explains it. */}
      <section className="mt-16 max-w-[62ch]">
        <h2 className="text-4xl">Picking the topic</h2>
        <p className="mt-4 text-lg leading-[2.1]">
          <span className="sticker mr-2 inline-block bg-mint px-3 text-2xl font-extrabold tabular-nums" style={{ transform: "rotate(-2deg)" }}>
            {router.correct} of {router.n}
          </span>
          test questions went to the right topic. I pick it by comparing your question with each library: no AI call, about 15 milliseconds. On deliberately ambiguous questions I search both libraries instead of guessing.
        </p>
      </section>

      {/* 3. Does the multi-step "agent" help? */}
      {b.pipeline_ablation && (
        <section className="mt-16">
          <h2 className="text-4xl">Does splitting questions help?</h2>
          <div className="mt-6 overflow-x-auto">
            <table className="card bg-card text-left">
              <thead className="bg-baby">
                <tr>{["Topic", "Approach", "Found it", "Citations correct", "Said \"I don't know\" when it should"].map((h) => <th key={h} className="border-b-[3px] border-ink px-4 py-2">{h}</th>)}</tr>
              </thead>
              <tbody>
                {Object.entries(b.pipeline_ablation).flatMap(([topic, arms]) =>
                  (["naive", "agentic"] as const).map((a) => (
                    <tr key={topic + a} className="border-b-2 border-ink/20">
                      <td className="px-4 py-2 font-bold">{TOPIC[topic] ?? topic}</td>
                      <td className="px-4 py-2">{a === "naive" ? "One plain search" : "Split + plan"}</td>
                      <td className="px-4 py-2 tabular-nums">{arms[a]["recall@5"].toFixed(3)}</td>
                      <td className="px-4 py-2 tabular-nums">{arms[a].citation_accuracy.toFixed(3)}</td>
                      <td className="px-4 py-2 tabular-nums">{arms[a].abstention_rate.toFixed(3)}</td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
          <p className="mt-4 max-w-[62ch]">
            {splitMatters
              ? "Splitting questions changed the results; see the rows above for which way."
              : "On this test set, splitting questions made no measurable difference. That's reported because it's true: the test questions are mostly single-part."}
          </p>
        </section>
      )}

      {/* 4. Who did what: one shelf of stickers, sized by how much they say. */}
      <section className="mt-16">
        <h2 className="text-4xl">Who did what</h2>
        <div className="mt-6 flex flex-wrap items-start gap-4">
          <span className="sticker bg-card px-3 py-2 font-bold" style={{ transform: "rotate(-1.5deg)" }}>
            Writer: {b.models.generator}
          </span>
          <span className="sticker max-w-md bg-lilac px-4 py-3" style={{ transform: "rotate(1deg)" }}>
            <b>Checker: {b.models.judge}</b>, from a different company, so it isn&apos;t grading its own team&apos;s work. Not yet compared against human grading.
          </span>
          <span className="sticker max-w-sm bg-baby px-4 py-3" style={{ transform: "rotate(-0.5deg)" }}>
            <b>10 blind questions</b> from a mentor and classmates who never saw the data, kept separate from these results.
          </span>
        </div>
      </section>

      <p className="mt-10 text-sm font-semibold">Results generated {new Date(b.generated_at).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}.</p>
    </main>
  );
}
