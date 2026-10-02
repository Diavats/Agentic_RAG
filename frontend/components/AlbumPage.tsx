"use client";
// One "album page" = one question and its answer.
// Five numbered slots (the pipeline steps) fill in as the answer streams.
// An empty dashed slot means "not done yet" or "nothing found": honesty you can see.

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Prismo from "./Prismo";
import { STAGES, type Source, type Stage, type Trace } from "@/lib/api";

export type Entry = {
  id: number;
  question: string;
  stages: Partial<Trace>;   // filled in stage by stage as events arrive
  done: boolean;
  error?: string;
};

// What each slot is called while waiting, and what it says once filled.
const SLOT: Record<Stage, { waiting: string; bg: string; tilt: string; filled: (t: Partial<Trace>) => string }> = {
  routing: { waiting: "Pick a topic", bg: "var(--lilac)", tilt: "-1.5deg",
    filled: (t) => `Topic: ${t.routing!.domain === "financial" ? "finance" : t.routing!.domain}` },
  planning: { waiting: "Plan the search", bg: "var(--sun)", tilt: "1deg",
    filled: (t) => t.planning!.subqueries.length > 1 ? `Split into ${t.planning!.subqueries.length} searches` : "One search" },
  retrieval: { waiting: "Find sources", bg: "var(--baby)", tilt: "-0.5deg",
    filled: (t) => `Found ${t.retrieval!.sources.length} passages` },
  synthesis: { waiting: "Write the answer", bg: "var(--mint)", tilt: "1.5deg",
    filled: () => "Answer written" },
  verification: { waiting: "Check my work", bg: "var(--hot)", tilt: "-1deg",
    filled: (t) => `${t.verification!.supported_claims} of ${t.verification!.total_claims} claims checked out` },
};

// The model writes [S1] or 【S1】; turn both into links the renderer swaps for stickers.
const linkCitations = (text: string) => text.replace(/[\[【]\s*(S\d+)\s*[\]】]/g, "[$1](#cite-$1)");

export default function AlbumPage({ entry }: { entry: Entry }) {
  const t = entry.stages;
  const [open, setOpen] = useState<string | null>(null); // which source sticker is open

  // The first step that hasn't arrived yet is the one running right now.
  const running = entry.done || entry.error ? null : STAGES.find((s) => !t[s]);

  // Map "S1" -> the source it points at (marker = rank).
  const sources = t.retrieval?.sources ?? [];
  const cited = (t.synthesis?.citations ?? []).filter((c) => c.resolved);
  const byMarker = new Map(sources.map((s) => [`S${s.rank}`, s]));

  return (
    <article className="card p-5 sm:p-6" aria-busy={!!running}>
      {/* Your question, as a lilac sticker. */}
      <p className="sticker ml-auto w-fit max-w-[85%] bg-lilac px-4 py-2 font-bold" style={{ transform: "rotate(1deg)" }}>
        {entry.question}
      </p>

      {/* The five numbered slots. */}
      <ol className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-5" aria-label="How I answered">
        {STAGES.map((stage, i) => {
          const data = t[stage] as { latency_ms?: number } | null | undefined;
          const filled = !!data;
          const live = running === stage;
          const skipped = entry.done && !filled; // e.g. no self-check ran
          return (
            <li
              key={stage}
              className={`relative min-h-[86px] rounded-[10px] p-3 text-sm font-bold ${filled ? "sticker press-in" : "border-[3px] border-dashed border-ink/40 text-ink/70"} ${live ? "live" : ""}`}
              style={filled ? { background: SLOT[stage].bg, ["--tilt" as string]: SLOT[stage].tilt, transform: `rotate(${SLOT[stage].tilt})` } : undefined}
            >
              <span className="block text-xs tabular-nums">{String(i + 1).padStart(2, "0")}</span>
              {filled ? SLOT[stage].filled(t) : live ? `${SLOT[stage].waiting}…` : skipped ? "Skipped" : SLOT[stage].waiting}
              {filled && data?.latency_ms != null && (
                <span className="mt-1 block text-xs font-semibold tabular-nums">{(data.latency_ms / 1000).toFixed(1)}s</span>
              )}
            </li>
          );
        })}
      </ol>

      {/* Prismo + the answer. */}
      <div className="mt-6 flex items-start gap-4">
        <Prismo mood={entry.error ? "sorry" : running ? "thinking" : "happy"} size={64} className="shrink-0" />
        <div className="min-w-0 flex-1">
          {entry.error ? (
            <p className="font-semibold">{entry.error}</p>
          ) : t.synthesis ? (
            <div className="answer max-w-[70ch]">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // A citation link becomes a pink sticker that opens its source.
                  a: ({ href, children }) =>
                    href?.startsWith("#cite-") ? (
                      <button
                        type="button"
                        onClick={() => setOpen(open === href.slice(6) ? null : href.slice(6))}
                        className="mx-0.5 rounded-md border-2 border-ink bg-hot px-1 text-xs font-extrabold align-middle"
                        aria-label={`Show source ${href.slice(6)}`}
                      >
                        {children}
                      </button>
                    ) : (
                      <a href={href} className="underline">{children}</a>
                    ),
                }}
              >
                {linkCitations(t.synthesis.answer)}
              </ReactMarkdown>
            </div>
          ) : (
            <p className="font-semibold text-ink/70">{running ? "Working on it…" : ""}</p>
          )}
        </div>
      </div>

      {/* Source stickers: the passages the answer actually cited. */}
      {t.synthesis && !entry.error && (
        <div className="mt-6">
          <div className="flex flex-wrap gap-3">
            {cited.length === 0 ? (
              <span className="rounded-[14px] border-[3px] border-dashed border-ink/70 px-3 py-2 text-sm font-bold text-ink/70">
                No source matched, so I didn't guess
              </span>
            ) : (
              cited.map((c, i) => (
                <SourceSticker
                  key={c.marker}
                  marker={c.marker}
                  source={byMarker.get(c.marker)}
                  open={open === c.marker}
                  onToggle={() => setOpen(open === c.marker ? null : c.marker)}
                  tilt={i % 2 ? "1.5deg" : "-1.5deg"}
                />
              ))
            )}
          </div>
          {sources.length > cited.length && (
            <p className="mt-3 text-sm font-semibold text-ink/70">
              I also checked {sources.length - cited.length} other passages that weren't needed.
            </p>
          )}
        </div>
      )}

      {/* Self-check note + disclaimer, once finished. */}
      {entry.done && t.verification && (
        <p className="mt-5 text-sm">
          <b>Self-check:</b> a second AI model checked each claim against the sources. It's a signal, not proof.
        </p>
      )}
      {entry.done && <p className="mt-2 text-sm text-ink/70">Not medical or financial advice.</p>}
    </article>
  );
}

// One citation sticker. Opening it shows the exact passage and its search score.
function SourceSticker({ marker, source, open, onToggle, tilt }: {
  marker: string; source?: Source; open: boolean; onToggle: () => void; tilt: string;
}) {
  if (!source) return null;
  const kind = source.source_type === "tabular" ? "spreadsheet row" : "document";
  return (
    <div className="relative">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="lift sticker bg-card px-3 py-2 text-left text-sm font-bold"
        style={{ ["--tilt" as string]: tilt, transform: `rotate(${tilt})` }}
      >
        <span className="mr-2 rounded-md border-2 border-ink bg-hot px-1 text-xs">{marker}</span>
        {source.source_file || "uploaded file"}
        <span className="ml-1 font-semibold text-ink/60">({kind})</span>
        {/* The passage's opening words, so two stickers from one file differ. */}
        <span className="mt-0.5 block max-w-[260px] truncate text-xs font-semibold text-ink/70">
          &ldquo;{source.text.split(/\s+/).slice(0, 8).join(" ")}…&rdquo;
        </span>
      </button>
      {open && (
        <div className="pop card absolute left-0 top-full z-20 mt-3 w-[min(420px,80vw)] bg-card p-4 text-sm">
          <p className="max-h-56 overflow-y-auto whitespace-pre-line">{source.text}</p>
          <p className="mt-3 border-t-2 border-ink pt-2 font-bold tabular-nums">
            Rank {source.rank}, search score {source.score.toFixed(4)}
          </p>
        </div>
      )}
    </div>
  );
}
