# ADR-001: Chat frontend, upload domain gate, visitor quota

**Status:** Accepted
**Date:** 2026-10-03
**Deciders:** Dia

## Context

The backend (FastAPI on Render, `prism-api-y5op.onrender.com`) is live and
tested. It has no UI. Required:

- A warm, chatbot-style UI with a guide character and cited sources.
- Visitors can upload their own files, but only finance or medical content.
- Formats stay CSV, Excel, DOCX (decided: no PDF/TXT).
- The app is public, and Groq's free tier has a daily cap.

Constraints: Render free tier (512 MB, sleeps after 15 min, ~1 min cold
wake), 8 GB dev laptop, BTech timeline, every decision must be defensible in
a viva.

## Decision

1. **Next.js (App Router) on Vercel calling the Render API directly.** No
   proxy. CORS is already open; add `DELETE` to the allowed methods.
2. **Four pages:** Welcome · Chat (with a Files drawer) · How it works ·
   Benchmarks. Limits are explained in-context by the mascot and in a
   "What I can't do" section, not on a separate page.
3. **Upload domain gate on the server, reusing the embedding router.**
   Measured 2026-10-03 against the indexed corpora (max cosine):

   | text | top score |
   |---|---|
   | on-topic (4 samples, medical + finance, prose + rows) | 0.338 – 0.620 |
   | off-topic (recipe, football, poem, code) | 0.010 – 0.104 |

   Threshold **0.20**. Below it → refuse ("not finance or medical"). Above
   it → return the guess; the user may switch finance↔medical but cannot
   force an off-topic file in. The check runs on raw text **before** any
   LLM call, so refusing costs zero quota (same principle as the row cap).
4. **DOCX can be finance.** The text extractor takes the domain instead of
   hardcoding medical.
5. **Per-visitor daily quota in FastAPI:** 15 questions, 3 uploads per
   visitor per day, keyed by client IP (first `X-Forwarded-For` hop on
   Render). In memory.

## Options considered

### A — Next.js on Vercel → Render API directly (chosen)
| Dimension | Assessment |
|---|---|
| Complexity | Low: one frontend, one backend |
| Cost | Free (Vercel hobby + Render free) |
| Security | Quota enforced server-side; the browser cannot bypass it |
| Familiarity | Next.js is what 21st.dev components target |

### B — Next.js API routes as a proxy
Adds a second server that only forwards requests. Rejected: no capability
the backend lacks.

### C — Static Vite SPA
Smaller, but Dia chose Next.js on Vercel, and the component library targets it.

### Quota: access code vs per-visitor limit
An access code locks out recruiters who only have the link. A per-visitor
limit lets anyone try it while capping cost. Chosen: per-visitor limit.

## Consequences

- Easier: one deploy per side, both auto-deploy on push to `main`.
- Harder: the quota and the upload sessions live in memory, so a Render
  restart or sleep resets both. Acceptable for a demo; the UI says uploads
  expire. Upgrade path: Redis/Postgres.
- The 0.20 threshold was calibrated on 8 samples against a 26-unit corpus.
  On-domain text that is far from the corpus (e.g. cardiology) may score
  lower. Revisit when the real medical dataset arrives.
- Judge–human agreement was not measured (Dia declined hand-scoring). The
  eval report must state that the judge is unvalidated against humans.

## Action items

1. [ ] Backend: domain gate + `/session/{id}/classify`, DOCX domain, quota, CORS DELETE (+ tests)
2. [ ] Frontend: Next.js app in `frontend/`, 4 pages, mascot, streaming chat
3. [ ] Verify each page with Playwright against the live API
4. [ ] Deploy `frontend/` to Vercel from GitHub (auto-deploy on push)
5. [ ] EVAL_RESULTS.md: state that the judge is not human-validated
