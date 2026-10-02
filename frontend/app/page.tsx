// Welcome page: Prismo says hi, explains PRISM in one breath,
// and offers three sample questions you can tap to start.

import Link from "next/link";
import Prismo from "@/components/Prismo";
import data from "@/lib/sample-trace.json";

// A real answer from the live system, shown as a miniature album page.
const t = data.trace;
const MINI_SLOTS = [
  { label: "Topic: medical", bg: "bg-lilac", tilt: "-1.5deg" },
  { label: `Split into ${t.planning.subqueries.length} searches`, bg: "bg-sun", tilt: "1deg" },
  { label: `Found ${t.retrieval.sources.length} passages`, bg: "bg-baby", tilt: "-0.5deg" },
  { label: "Answer written", bg: "bg-mint", tilt: "1.5deg" },
  { label: `${t.verification?.supported_claims} of ${t.verification?.total_claims} claims checked out`, bg: "bg-hot", tilt: "-1deg" },
];
const firstSource = t.retrieval.sources[0];

// Real questions the curated files can answer (they're in the eval set).
const SAMPLES = [
  { q: "What are the exclusion criteria for the study?", bg: "bg-lilac", tilt: "-2deg" },
  { q: "What does JGCHEM supply, and to whom?", bg: "bg-mint", tilt: "1.5deg" },
  { q: "Which samples showed strong antigen activation?", bg: "bg-baby", tilt: "-1deg" },
];

export default function Welcome() {
  return (
    <main className="mx-auto max-w-6xl px-4 pb-24 pt-10 sm:pt-16">
      {/* ---------- First screen: wordmark, Prismo, sample questions ---------- */}
      <section className="grid items-center gap-10 md:grid-cols-[1.4fr_1fr]">
        <div>
          {/* The giant PRISM sticker. */}
          <h1
            className="sticker arrive inline-block bg-sun px-5 py-1 text-[clamp(64px,13vw,168px)] leading-none tracking-tight"
            style={{ ["--tilt" as string]: "-4deg", transform: "rotate(-4deg)", boxShadow: "inset 0 0 0 5px #fff, 10px 10px 0 #000" }}
          >
            PRISM
          </h1>

          <p className="arrive mt-8 max-w-[34ch] text-2xl font-semibold" style={{ ["--i" as string]: 1 }}>
            I read finance and medical files, answer your questions, and show you exactly where each answer came from.
          </p>

          {/* Sample questions: tap one to ask it straight away. */}
          <div className="mt-8 flex flex-wrap gap-4">
            {SAMPLES.map((s, i) => (
              <Link
                key={s.q}
                href={`/chat?q=${encodeURIComponent(s.q)}`}
                className={`lift sticker arrive ${s.bg} max-w-xs px-4 py-3 font-bold`}
                style={{ ["--tilt" as string]: s.tilt, ["--i" as string]: i + 2, transform: `rotate(${s.tilt})` }}
              >
                {s.q}
              </Link>
            ))}
          </div>

          <div className="arrive mt-10 flex flex-wrap items-center gap-4" style={{ ["--i" as string]: 5 }}>
            <Link href="/chat" className="btn text-lg">Start chatting</Link>
            <Link href="/how-it-works" className="font-bold underline decoration-[3px] underline-offset-4">
              See how I find answers
            </Link>
          </div>
        </div>

        {/* Prismo with a speech bubble. */}
        <div className="relative flex flex-col items-center">
          <div className="card arrive relative mb-6 max-w-xs bg-card p-4 text-lg font-semibold" style={{ ["--i" as string]: 1 }}>
            Hi, I'm Prismo! Ask me about the study protocol, the lab results, or the company reports, or upload your own file.
            {/* Bubble tail. */}
            <span aria-hidden className="absolute -bottom-[15px] left-1/2 h-6 w-6 -translate-x-1/2 rotate-45 border-b-[3px] border-r-[3px] border-ink bg-card" />
          </div>
          <Prismo mood="waving" size={220} />
        </div>
      </section>

      {/* ---------- What PRISM reads ---------- */}
      <section className="mt-24">
        <h2 className="text-4xl">What I can read</h2>
        <div className="mt-6 flex flex-wrap gap-3 text-lg font-bold">
          <span className="sticker bg-mint px-4 py-2">Finance</span>
          <span className="sticker bg-lilac px-4 py-2">Medical</span>
          <span className="sticker bg-card px-4 py-2">Word documents</span>
          <span className="sticker bg-card px-4 py-2">CSV and Excel sheets</span>
          <span className="sticker bg-baby px-4 py-2">Your own uploads, checked first</span>
        </div>
      </section>

      {/* ---------- A real answer, as a miniature album page ---------- */}
      <section className="mt-20">
        <h2 className="text-4xl">Every answer shows its work</h2>
        <p className="mt-2 max-w-[60ch] font-semibold">
          A real answer from the live system. Each numbered slot is a step I took; the sticker below is the passage I quoted.
        </p>
        <div className="card mt-8 max-w-3xl p-5" style={{ transform: "rotate(-0.6deg)" }}>
          <p className="sticker ml-auto w-fit max-w-[85%] bg-lilac px-4 py-2 font-bold">{t.question}</p>
          <ol className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {MINI_SLOTS.map((m, i) => (
              <li key={m.label} className={`sticker ${m.bg} min-h-[80px] p-3 text-sm font-bold`} style={{ transform: `rotate(${m.tilt})` }}>
                <span className="block text-xs tabular-nums">{String(i + 1).padStart(2, "0")}</span>
                {m.label}
              </li>
            ))}
          </ol>
          <div className="mt-5 max-w-md rounded-[6px] border-[3px] border-ink bg-card p-3 text-sm shadow-[5px_5px_0_#000]">
            <span className="mr-2 rounded-md border-2 border-ink bg-hot px-1 text-xs font-extrabold">S1</span>
            <b>{firstSource.source_file}</b>
            <p className="mt-2 line-clamp-3">{firstSource.text}</p>
          </div>
        </div>
        <div className="mt-10 flex flex-wrap gap-4">
          <Link href="/how-it-works" className="btn">See how each step works</Link>
          <Link href="/benchmarks" className="btn bg-card">See the real numbers</Link>
        </div>
      </section>

      <p className="mt-20 text-sm font-semibold">PRISM is a student project. Answers are not medical or financial advice.</p>
    </main>
  );
}
