"use client";
// The baby-blue drawer where you add your own files.
// Flow per file: check topic (free) → you confirm or switch finance/medical →
// upload (uses 1 of today's uploads) → indexing → ready. Off-topic files are refused.

import { useRef, useState } from "react";
import Prismo from "./Prismo";
import { classify, job as jobStatus, upload, type Domain } from "@/lib/api";

export type FileItem = {
  name: string;
  file: File;
  step: "checking" | "confirm" | "indexing" | "ready" | "refused";
  domain?: Domain;
  note?: string;
};

const LABEL: Record<Domain, string> = { financial: "Finance", medical: "Medical" };
const STAMP: Record<Domain, string> = { financial: "bg-mint", medical: "bg-lilac" };

export default function FilesDrawer({ open, onClose, getSession, files, setFiles, onCleared }: {
  open: boolean;
  onClose: () => void;
  getSession: () => Promise<string>;           // creates the session on first use
  files: FileItem[];
  setFiles: (update: (prev: FileItem[]) => FileItem[]) => void;
  onCleared: () => void;
}) {
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  // Change one file's card without touching the others.
  const patch = (name: string, change: Partial<FileItem>) =>
    setFiles((prev) => prev.map((f) => (f.name === name ? { ...f, ...change } : f)));

  // Step 1: ask the server which topic this file is (costs nothing).
  async function add(file: File) {
    setFiles((prev) => [...prev.filter((f) => f.name !== file.name), { name: file.name, file, step: "checking" }]);
    try {
      const { domain } = await classify(await getSession(), file);
      patch(file.name, { step: "confirm", domain });
    } catch (e) {
      patch(file.name, { step: "refused", note: (e as Error).message });
    }
  }

  // Step 2: the user confirmed the topic; upload and wait for indexing to finish.
  async function confirm(item: FileItem, domain: Domain) {
    patch(item.name, { step: "indexing", domain });
    try {
      const session = await getSession();
      const { job_id } = await upload(session, item.file, domain);
      window.dispatchEvent(new Event("prism:quota"));
      // Poll every 1.5s until the job is done (spreadsheets take one AI call per row).
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        const j = await jobStatus(session, job_id);
        if (j.status === "done") return patch(item.name, { step: "ready", note: `${j.unit_count} pieces indexed` });
        if (j.status === "failed") return patch(item.name, { step: "refused", note: j.message });
      }
    } catch (e) {
      patch(item.name, { step: "refused", note: (e as Error).message });
    }
  }

  return (
    <>
      {/* Dim the page behind the drawer; click it to close. */}
      <div
        onClick={onClose}
        className={`fixed inset-0 z-40 bg-ink/30 transition-opacity duration-200 ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
      />
      <aside
        aria-label="My files"
        aria-hidden={!open}
        inert={!open}
        className="fixed bottom-0 right-0 z-50 flex max-h-[85dvh] w-full flex-col border-t-[3px] border-ink bg-baby p-5 sm:top-0 sm:max-h-none sm:w-[420px] sm:border-l-[3px] sm:border-t-0"
        style={{
          transform: open ? "translate(0,0)" : "var(--drawer-hidden)",
          transition: `transform ${open ? "320ms" : "200ms"} var(--ease-drawer)`,
        }}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-3xl">My files</h2>
          <button className="btn bg-card px-3 py-1" onClick={onClose}>Close</button>
        </div>
        <p className="mt-2 text-sm font-semibold">
          Finance or medical only: CSV, Excel or Word, up to 2 MB, spreadsheets up to 25 rows.
          Files disappear after an hour.
        </p>

        {/* Drop zone: drag a file here, or click to pick one. */}
        <button
          type="button"
          onClick={() => picker.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            Array.from(e.dataTransfer.files).forEach(add);
          }}
          className={`mt-4 flex items-center gap-3 rounded-[14px] p-4 text-left font-bold ${dragging ? "ants bg-sun" : "border-[3px] border-dashed border-ink bg-card"}`}
        >
          <Prismo mood={dragging ? "happy" : "idle"} size={48} />
          {dragging ? "Drop it, I'll check what it is" : "Drop a file here or click to choose"}
        </button>
        <input
          ref={picker}
          type="file"
          hidden
          accept=".csv,.xlsx,.xls,.docx"
          onChange={(e) => { Array.from(e.target.files ?? []).forEach(add); e.target.value = ""; }}
        />

        {/* One sticker per file, showing where it is in the flow. */}
        <ul className="mt-5 flex-1 space-y-4 overflow-y-auto pb-2 pr-1">
          {files.map((f) => (
            <li key={f.name} className="sticker press-in bg-card p-3" style={{ ["--tilt" as string]: "0deg" }}>
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-bold">{f.name}</span>
                {f.domain && f.step !== "refused" && (
                  <span className={`sticker ${STAMP[f.domain]} shrink-0 px-2 text-xs font-extrabold`}>{LABEL[f.domain]}</span>
                )}
              </div>

              {f.step === "checking" && <p className="live mt-2 rounded-md border-2 px-2 text-sm font-bold">Checking: finance or medical?</p>}

              {f.step === "confirm" && f.domain && (
                <div className="mt-3">
                  <p className="text-sm">This looks like <b>{LABEL[f.domain].toLowerCase()}</b>. Add it?</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button className="btn px-3 py-1 text-sm" onClick={() => confirm(f, f.domain!)}>Add as {LABEL[f.domain].toLowerCase()}</button>
                    <button
                      className="btn bg-card px-3 py-1 text-sm"
                      onClick={() => confirm(f, f.domain === "medical" ? "financial" : "medical")}
                    >
                      Use {f.domain === "medical" ? "finance" : "medical"} instead
                    </button>
                  </div>
                </div>
              )}

              {f.step === "indexing" && <p className="live mt-2 rounded-md border-2 px-2 text-sm font-bold">Reading and indexing…</p>}
              {f.step === "ready" && <p className="mt-2 text-sm font-bold">Ready to ask about ({f.note})</p>}
              {f.step === "refused" && <p className="mt-2 text-sm font-semibold">{f.note}</p>}
            </li>
          ))}
        </ul>

        {files.length > 0 && (
          <button className="btn mt-3 bg-card" onClick={onCleared}>Clear my files</button>
        )}
      </aside>
    </>
  );
}
