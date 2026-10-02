# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Next.js (App Router) + Tailwind on Vercel, in `frontend/`. Calls the FastAPI
backend on Render (`https://prism-api-y5op.onrender.com`) directly. Decided in
ADR-001.

## Users

1. **Viva panel and mentor**, watching a live demo and probing every decision.
2. **Recruiters** opening the link from a CV, with about 60 seconds of attention.
3. **Curious visitors** who ask questions and upload their own finance or
   medical file.

## Product Purpose

Ask plain-English questions about finance and medical documents and get
answers with sources you can check. Success: a visitor gets a cited answer
fast, and a technical reader leaves convinced the system was *measured*, not
just built.

## Positioning

Not "a RAG chatbot". What a neighbouring project cannot truthfully copy:

- **Hybrid retrieval, measured.** Dense (MiniLM) + sparse (BM25) fused with
  Reciprocal Rank Fusion, and an ablation that reports where hybrid wins
  *and where it loses*.
- **An evaluation designed to be hard to fool:** a golden set, three
  ablations (retrieval method, naive vs agentic pipeline, router), a judge
  from a different model vendor than the generator, and **blind questions**
  written by a mentor and classmates who never saw the corpus.
- **One schema, two domains, two formats.** Word-document prose and
  spreadsheet rows become the same KnowledgeUnit; nothing downstream branches
  on domain or format.
- **Every pipeline step is visible:** route → plan → retrieve → answer →
  verify, streamed live.
- **Honest numbers,** including the bad ones ("naive == agentic" is reported
  because it is true).

## Operating Context

A live demo in a viva room, a CV link opened on a phone or laptop, and the
eval report (`docs/EVAL_RESULTS.md`) as the evidence behind every claim.

## Capabilities and Constraints

- Two domains only: finance and medical. Uploads are checked and off-topic
  files refused.
- Upload formats: CSV, Excel, DOCX. Spreadsheets capped at 25 rows (one LLM
  call per row). Max 2 MB. Uploads expire after 1 hour or a server restart.
- 15 questions and 3 uploads per visitor per day.
- Free Render backend: about 1 minute to wake after 15 minutes idle; 512 MB.
- Known weaknesses that must stay visible: superlatives and aggregates ("which
  is highest") are unreliable, the golden set is small (n=11 per domain), and
  the judge is not validated against human scores.

## Brand Commitments

- Name: **PRISM**. Guide character: a small prism crystal (it splits a
  question into sources the way a prism splits light).
- Visual constraint chosen by the owner: neo-brutalism; pop pink, lilac,
  black, yellow.

## Evidence on Hand

- `GET /benchmark`: real eval numbers (docs/eval_results.json).
- `docs/TRACES.md`: real runs, including wrong answers.
- `src/eval/blind_questions.txt`: 10 blind questions.
- No testimonials, users, or adoption numbers exist; never invent them.

## Product Principles

1. Show the evidence: every answer cites sources you can open.
2. Report what was measured, including failures.
3. Never present output as medical or financial advice.
4. Warm, not cute-at-the-expense-of-clarity: the guide explains, it doesn't decorate.

## Accessibility & Inclusion

WCAG AA contrast, fully keyboard-usable, and all motion disabled under
`prefers-reduced-motion`.
