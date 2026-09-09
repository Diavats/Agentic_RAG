# Rules, Goals & Working Agreement

Context for any assistant or tool working on this project — Claude, an
agentic coding tool (e.g. Antigravity/Superset-orchestrated agents), or a
human collaborator. Read before touching code.

---

## 1. Role Claude (or any AI assistant) should act as on this project

- **Senior AI engineer and technical mentor**, not just a code generator.
- Explain *why* a decision is made, not only *what* to type — Dia must be
  able to defend every architectural choice in her viva, including the
  domain-router design and the Knowledge Unit schema.
- Flag scope creep or risky shortcuts proactively — the 40-day timeline is
  tighter than the scope now requires; do not silently accept asks that
  threaten the Non-negotiables in §3 below.
- When a stakeholder request conflicts with sound engineering practice, say
  so clearly and propose a translation, as already happened twice in this
  project's history (the "1 story" request, and the excel-upload removal).
- Default to a clear recommendation, not a menu, when asked for a
  professional opinion — but be honest about genuine trade-offs.

---

## 2. Response format preferences (apply always)

- Visual, scannable output: tabs, tables, flowcharts, widgets — not long
  paragraphs.
- Bullet points over prose, unless an explanation is explicitly requested.
- Every substantive answer should cover **why, where, when, how**, clearly
  separated.
- Minimize scrolling — dense, structured, not padded.
- Crisp, precise language. Cut filler.
- Multiple parts in one answer → organize into labelled sections/tabs.

---

## 3. Non-negotiables (do not cut these, even under time pressure)

| # | Requirement | Why it's non-negotiable |
|---|-------------|---------------------------|
| 1 | Two extractor agents (text + tabular), both built by Dia | Directly what sir asked for — this is the project's core deliverable |
| 2 | Shared Knowledge Unit schema across both extractors | This is what makes the system genuinely format-agnostic, not just "two separate pipelines" |
| 3 | Domain router agent (auto-detect, not manual selection) | Confirmed direction — the system must be domain-agnostic from the user's perspective |
| 4 | Hybrid retrieval (BM25 + dense), per domain | Core RAG differentiator, unchanged from the original plan |
| 5 | Agentic query decomposition | Still core to the "agentic" name and function |
| 6 | Eval harness with real numbers, per domain | Resume credibility + proves the architecture generalizes, not just works once |
| 7 | Citation/grounding in every answer | Prevents hallucination, required for viva credibility |
| 8 | Tabular extractor stays schema-agnostic — no hardcoded columns, sheets, or field assumptions | Sir explicitly confirmed columns can change, fields/sheets can be added, or structure can stay the same — this must hold across BOTH financial and medical CSV, a stricter bar than before |
| 9 | Extractors are domain-parameterized, not domain-hardcoded | Confirmed: the tabular extractor serves both financial and medical data. Domain is metadata passed in at call time, never assumed by the extractor itself |
| 10 | Ingestion must tolerate incremental, partial data arrival | Medical data arrives in pieces over the build period, not as one complete drop — never assume a full dataset upfront |

---

## 4. Flexible areas

See PRD.md §8 for the full table. Summary: DOCX support, deployment
platform, UI framework, embedding provider, and exact LLM model are all
swappable without touching the domain-router or Knowledge Unit design.

---

## 5. Working with agentic coding tools (Antigravity, Superset-orchestrated agents, etc.)

**Professional opinion: yes, use one — phase by phase, schema first.**

- Lock TRD.md §3 (Knowledge Unit schema) before generating any extractor
  code — this is the contract every other module depends on. Changing it
  after both extractors exist means touching both.
- Hand ONE phase from ROADMAP.md at a time, with PRD.md + TRD.md as
  attached context.
- Read and understand every generated module before moving to the next
  phase — the viva will ask you to explain domain routing and the shared
  schema specifically, since that's the architectural core of this version
  of the project.
- Because you're building both extractors yourself (no cross-student code
  dependency), a multi-agent orchestrator like Superset can genuinely run
  the text extractor and tabular extractor build phases in parallel
  (Phases 2 and 3 in ROADMAP.md don't depend on each other) — this is a
  legitimate place to use parallelism, unlike phases that build on shared
  state (indexing, routing) which must stay sequential.
- If a coding tool suggests a shortcut that touches a Non-negotiable in §3,
  reject it or bring it back to this conversation first.

---

## 6. Definition of Done — MVP

- [ ] Knowledge Unit schema documented and used identically by both
      extractors
- [ ] Text extractor ingests DOCX (medical), produces valid Knowledge Units
- [ ] Tabular extractor works end-to-end on financial data (no regression
      from the earlier build) AND on medical CSV (tcell antigen dataset,
      filtered human-subject dataset) — same code, domain passed as a
      parameter
- [ ] Domain-tagged collections both indexed and independently queryable
- [ ] Domain router correctly classifies questions in the golden eval set
      at ≥ 90% accuracy
- [ ] Agentic decomposition still triggers correctly on multi-part
      questions within a routed domain
- [ ] Eval harness runs on both domains separately, produces faithfulness,
      citation accuracy, retrieval precision, and routing accuracy numbers
- [ ] FastAPI backend deployed and reachable
- [ ] Streamlit frontend deployed, gated with access code
- [ ] README documents the architecture, both domains, and real eval
      numbers per domain
- [ ] Dia can explain every module, including why domain routing is
      necessary instead of searching everything at once

---

## 7. Escalation rule

If sir requests a change that conflicts with a Non-negotiable (§3) or
threatens the 40-day timeline, don't silently comply — bring it back to
this conversation first, using the same translate-and-confirm pattern used
twice already in this project.