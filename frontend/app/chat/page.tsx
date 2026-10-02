"use client";
// Chat page: ask a question, watch its album page fill in live.
// You can ask PRISM's own files, or switch to the files you uploaded.

import { useEffect, useRef, useState } from "react";
import AlbumPage, { type Entry } from "@/components/AlbumPage";
import FilesDrawer, { type FileItem } from "@/components/FilesDrawer";
import Prismo from "@/components/Prismo";
import { askStream, dropSession, newSession } from "@/lib/api";

// Placeholders that rotate in the empty input, as gentle hints.
const HINTS = [
  "What are the exclusion criteria?",
  "Which company had the strongest sales growth?",
  "How should blood samples be stored?",
];

export default function Chat() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState(0);
  const [drawer, setDrawer] = useState(false);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [scope, setScope] = useState<"library" | "mine">("library");
  const session = useRef<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const readyFiles = files.filter((f) => f.step === "ready").length;

  // Create the upload session the first time it's needed, then reuse it.
  async function getSession() {
    if (!session.current) session.current = (await newSession()).session_id;
    return session.current;
  }

  // Ask one question and fill its album page as each pipeline step arrives.
  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const id = Date.now();
    setBusy(true);
    setText("");
    setEntries((prev) => [...prev, { id, question: q, stages: {}, done: false }]);
    const update = (change: Partial<Entry> | ((e: Entry) => Partial<Entry>)) =>
      setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, ...(typeof change === "function" ? change(e) : change) } : e)));
    requestAnimationFrame(() => bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" }));

    try {
      await askStream(q, scope === "mine" ? session.current : null, (stage, data) => {
        if (stage === "done") update({ stages: data, done: true });
        else if (stage === "error") update({ error: `Something broke on my side: ${data.message}`, done: true });
        else if (stage !== "started") update((e) => ({ stages: { ...e.stages, [stage]: data } }));
      });
      update({ done: true });
    } catch (e) {
      update({ error: (e as Error).message, done: true });
    } finally {
      setBusy(false);
      window.dispatchEvent(new Event("prism:quota"));
    }
  }

  // Arriving from a Welcome sample sticker (?q=...) asks it straight away.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      window.history.replaceState(null, "", "/chat");
      ask(q);
    }
    // Rotate the placeholder hint every 4 seconds.
    const timer = setInterval(() => setHint((h) => (h + 1) % HINTS.length), 4000);
    return () => clearInterval(timer);
  }, []);

  return (
    <main className="mx-auto flex min-h-[calc(100dvh-72px)] max-w-3xl flex-col px-4 pb-6 pt-8">
      {/* Empty state: Prismo invites the first question. */}
      {entries.length === 0 && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 py-10 text-center">
          <Prismo mood="idle" size={140} />
          <h1 className="text-4xl">Ask me anything about the files</h1>
          <p className="max-w-[44ch] font-semibold">
            I'll show each step as I work: picking the topic, searching, writing, then checking my answer.
          </p>
        </div>
      )}

      {/* One album page per question. */}
      <div className="flex flex-col gap-8">
        {entries.map((e) => <AlbumPage key={e.id} entry={e} />)}
      </div>
      <div ref={bottom} />

      {/* The input dock, stuck to the bottom of the screen. */}
      <form
        onSubmit={(e) => { e.preventDefault(); ask(text); }}
        className="sticky bottom-4 mt-8 rounded-[16px] border-[3px] border-ink bg-sun p-3 shadow-[6px_6px_0_#000]"
      >
        {/* Which files to search, shown once you've uploaded something. */}
        {readyFiles > 0 && (
          <div role="radiogroup" aria-label="Search in" className="mb-3 flex gap-2 text-sm font-bold">
            {(["library", "mine"] as const).map((s) => (
              <button
                key={s}
                type="button"
                role="radio"
                aria-checked={scope === s}
                onClick={() => setScope(s)}
                className={`sticker px-3 py-1 ${scope === s ? "bg-hot" : "bg-card"}`}
              >
                {s === "library" ? "PRISM's files" : `My files (${readyFiles})`}
              </button>
            ))}
          </div>
        )}

        <div className="flex items-end gap-3">
          <button type="button" className="btn shrink-0 bg-baby px-3" onClick={() => setDrawer(true)} aria-label="Open my files">
            Files{files.length ? ` (${files.length})` : ""}
          </button>
          {/* Grows with your text; Enter sends, Shift+Enter adds a line. */}
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(text); }
            }}
            rows={1}
            maxLength={1000}
            placeholder={HINTS[hint]}
            aria-label="Your question"
            className="max-h-40 min-h-[48px] flex-1 resize-none rounded-[12px] border-[3px] border-ink bg-card px-3 py-2.5 font-semibold [field-sizing:content] placeholder:text-ink/70 focus:outline-none focus-visible:outline-[3px] focus-visible:outline-hot"
          />
          <button type="submit" className="btn shrink-0 bg-hot" disabled={busy || !text.trim()}>
            {busy ? "Working…" : "Ask"}
          </button>
        </div>
      </form>

      <FilesDrawer
        open={drawer}
        onClose={() => setDrawer(false)}
        getSession={getSession}
        files={files}
        setFiles={setFiles}
        onCleared={() => {
          // Throw away the session and everything uploaded to it.
          if (session.current) dropSession(session.current);
          session.current = null;
          setFiles([]);
          setScope("library");
        }}
      />
    </main>
  );
}
