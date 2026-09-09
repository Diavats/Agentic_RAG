# Query Traces

Real, unedited runs of the pipeline — including the ones that fail.

Every RAG project claims multi-step planning and hybrid retrieval. Almost none show the intermediate state, so the claim stays an architecture diagram. These are the actual decisions the system made: how it split each question, which documents it fused, what it cited, and how long each stage took. The failures are here deliberately — a system whose author has read its output is worth more than one with a clean-looking score.

Regenerate with `python -m src.main ask ...` (appends to `logs/traces.jsonl`).

| | |
|---|---|
| Recorded | 2026-09-09 |
| Commit | `5e5e4b4` |
| Generator model | `openai/gpt-oss-20b` |
| Embeddings | `all-MiniLM-L6-v2` (256-token limit, 224-token chunks) |
| Corpus | financial 15 units · medical 11 units |
| Traces | 10, all warm |

## Latency (warm — see the cold-start note below)

| | ms |
|---|---|
| median end-to-end | 7684 |
| fastest | 1279 |
| slowest | 19758 |

TRD section 7 budgets < 8000 ms end-to-end. 4 of 10 warm traces exceed it, and synthesis dominates every one of them — Groq response time, not retrieval. Retrieval is consistently under 200 ms once warm.

**Cold start.** The first query after a process starts spends ~19.8 s loading the embedding model; the second identical query takes 37 ms. That is a 500x difference with nothing to do with retrieval quality, so cold and warm traces are never averaged here. `hybrid_retrieval.warm_up()` exists to move that cost to boot, and Phase 7 calls it from the FastAPI lifespan.

## Traces

1 FAIL · 8 PASS · 1 PASS*


### ✅ What does JGCHEM supply and to whom?

`financial` · `44ec9b322884` · 3350 ms

Simple single-entity lookup. Planner split it into 2 sub-queries even though one would have done — decomposition is slightly eager on simple questions, which costs a retrieval pass but not accuracy.

| stage | detail | ms |
|---|---|---|
| route | financial (explicit) | 0 |
| plan | 2 sub-queries (decomposed) | 1377 |
| retrieve | 5 of 5 candidates | 1041 |
| synthesize | 1 citation, 0 unresolved | 933 |

Sub-queries:
1. What does JGCHEM supply?
2. To whom does JGCHEM supply?

<details><summary>Sources fused and answer</summary>

| # | id | rrf |
|---|---|---|
| S1 | `financial_tabular_sample_stocks_9a90cc_0000` ←cited | 0.0328 |
| S2 | `financial_tabular_sample_stocks_9a90cc_0014` | 0.0323 |
| S3 | `financial_tabular_sample_stocks_9a90cc_0001` | 0.0317 |
| S4 | `financial_tabular_sample_stocks_9a90cc_0002` | 0.031 |
| S5 | `financial_tabular_sample_stocks_9a90cc_0008` | 0.0301 |

```
JGCHEM’s core business is the supply of **Zinc Oxide (ZnO)**, a key ingredient used in automobile manufacturing and tyre vulcanization.  Its primary customers are major automotive companies such as **Bajaj** and **Maruti**, along with various **tyre makers** that rely on ZnO for their production processes. [S1]
```

</details>

---

### ❌ Which stock had the strongest operating profit growth?

`financial` · `2e0ad590a7b0` · 1596 ms

**Wrong answer.** Said SHAREINDIA (71.79%). The true top is DIACABS at 1003.70%, then ARIHANTCAP 337.50%, then KROSS 206.20%. Two compounding failures: retrieval never surfaced DIACABS (top-k by semantic similarity, and 'strongest growth' is not semantically close to any one row), AND synthesis picked wrong even though ARIHANTCAP and KROSS *were* in its context. This is RAG's structural weak spot: superlatives and aggregates need a scan over all rows, not top-k retrieval. Honest limitation, documented rather than hidden.

| stage | detail | ms |
|---|---|---|
| route | financial (explicit) | 0 |
| plan | 1 sub-query | 885 |
| retrieve | 4 of 4 candidates | 77 |
| synthesize | 1 citation, 0 unresolved | 634 |

<details><summary>Sources fused and answer</summary>

| # | id | rrf |
|---|---|---|
| S1 | `financial_tabular_sample_stocks_9a90cc_0004` ←cited | 0.0328 |
| S2 | `financial_tabular_sample_stocks_9a90cc_0010` | 0.032 |
| S3 | `financial_tabular_sample_stocks_9a90cc_0013` | 0.0313 |
| S4 | `financial_tabular_sample_stocks_9a90cc_0012` | 0.0308 |

```
The stock with the strongest operating‑profit growth is **SHAREINDIA**, whose operating profit rose by **71.79 %** quarter‑over‑quarter in the second quarter of 2026 [S1].
```

</details>

---

### ✅ Compare the auto-linked stocks against the finance-linked stocks this quarter.

`financial` · `c06be03873db` · 3380 ms

The case decomposition exists for: 3 sub-queries, 8 unique sources fused, 4 citations. A single-shot retrieval would have had to cover both sectors from one embedding.

| stage | detail | ms |
|---|---|---|
| route | financial (explicit) | 0 |
| plan | 3 sub-queries (decomposed) | 925 |
| retrieve | 8 of 8 candidates | 172 |
| synthesize | 4 citations, 0 unresolved | 2283 |

Sub-queries:
1. What are the auto-linked stocks for this quarter and their performance metrics?
2. What are the finance-linked stocks for this quarter and their performance metrics?
3. How do the performance metrics of auto-linked stocks compare to those of finance-linked stocks?

<details><summary>Sources fused and answer</summary>

| # | id | rrf |
|---|---|---|
| S1 | `financial_tabular_sample_stocks_9a90cc_0012` ←cited | 0.032 |
| S2 | `financial_tabular_sample_stocks_9a90cc_0010` | 0.0313 |
| S3 | `financial_tabular_sample_stocks_9a90cc_0007` ←cited | 0.0312 |
| S4 | `financial_tabular_sample_stocks_9a90cc_0011` ←cited | 0.0311 |
| S5 | `financial_tabular_sample_stocks_9a90cc_0005` ←cited | 0.0311 |
| S6 | `financial_tabular_sample_stocks_9a90cc_0009` | 0.0311 |
| S7 | `financial_tabular_sample_stocks_9a90cc_0004` | 0.0307 |
| S8 | `financial_tabular_sample_stocks_9a90cc_0013` | 0.0304 |

```
**Auto‑linked stocks (automotive/vehicle sector)**  
- **KROSS** – In the most recent quarter the company posted a modest but positive performance: sales grew **0.27 %** QOQ, operating profit rose **2.06 %**, net profit increased **0.61 %** and EPS grew **0.60 %**【S1】.  

**Finance‑linked stocks (banking, financial services, and related sectors)**  

| Stock | Sales QOQ | Operating profit QOQ | Net profit QOQ | EPS QOQ |
|-------|-----------|----------------------|----------------|---------|
| **AUBANK** | **+8.10 %** | – | **+24.6 %** | **+24.5 %** | 【S5】 |
| **ALLDIGI** | –0.0323 % | –0.0682 % | –0.3793 % | –0.3726 % | 【S4】 |
| **Prudent** | –0.036 % | –0.043 % | +0.2712 % | +0.2647 % | 【S3】 |

**Comparison**

- **Sales growth**: The auto‑linked KROSS showed a very small positive sales increase (0.27 %), whereas the finance‑linked AUBANK led with a strong 8.1 % rise. ALLDIGI and Prudent both recorded slight sales declines (≈ 0.03–0.04 %).
- **Profitability**: KROSS’s operating and net profit growth were modest (2.06 % and 0.61 %) and EPS grew 0.60 %. In contrast, AUBANK’s profitability surged (net profit +24.6 %, EPS +24.5 %). ALLDIGI suffered declines across all metrics, while Prudent’s operating profit fell but net profit and EPS still grew modestly (~ 0.27 % and 0.26 %).
- **Overall trend**: The auto‑linked sector (KROSS) delivered steady but limited growth, whereas the finance‑linked sector showed a mixed picture: one strong performer (AUBANK), one weak performer (ALLDIGI), and one moderate performer (Prudent).

Thus, this quarter the finance‑linked stocks outperformed the auto‑linked stock in terms of sales and profitability, with AUBANK driving the positive trend, while the auto‑linked KROSS maintained modest gains.
```

</details>

---

### ✅ What is TCS's dividend policy?

`financial` · `eecf91c9004e` · 1279 ms

**Correct abstention.** TCS is not in the corpus and the system said so instead of confabulating. Zero citations is the right output here — this is what the Phase 6 abstention-rate metric measures.

| stage | detail | ms |
|---|---|---|
| route | financial (explicit) | 0 |
| plan | 1 sub-query | 558 |
| retrieve | 4 of 4 candidates | 59 |
| synthesize | 0 citations, 0 unresolved | 661 |

<details><summary>Sources fused and answer</summary>

| # | id | rrf |
|---|---|---|
| S1 | `financial_tabular_sample_stocks_9a90cc_0004` | 0.0313 |
| S2 | `financial_tabular_sample_stocks_9a90cc_0013` | 0.0312 |
| S3 | `financial_tabular_sample_stocks_9a90cc_0001` | 0.0311 |
| S4 | `financial_tabular_sample_stocks_9a90cc_0007` | 0.0309 |

```
The provided context does not contain any information about Tata Consultancy Services (TCS) or its dividend policy. Therefore, I cannot answer the question based on the retrieved material.
```

</details>

---

### ✅ What are the exclusion criteria for enrollment?

`medical` · `c691d65db9c2` · 2202 ms

Clean DOCX-only retrieval, 2 citations, both resolved.

| stage | detail | ms |
|---|---|---|
| route | medical (explicit) | 0 |
| plan | 1 sub-query | 867 |
| retrieve | 4 of 4 candidates | 120 |
| synthesize | 2 citations, 0 unresolved | 1214 |

<details><summary>Sources fused and answer</summary>

| # | id | rrf |
|---|---|---|
| S1 | `medical_textual_medical_guideline_placeholder_52f6a9_0000` ←cited | 0.0328 |
| S2 | `medical_textual_medical_guideline_placeholder_52f6a9_0002` ←cited | 0.032 |
| S3 | `medical_textual_medical_guideline_placeholder_52f6a9_0001` | 0.0315 |
| S4 | `medical_tabular_medical_placeholder_3fc69d_0003` | 0.0313 |

```
**Exclusion criteria for enrollment**

| Criterion | Source |
|-----------|--------|
| Active infection | [S1] |
| Uncontrolled chronic condition | [S1] |
| Pregnancy | [S1] |
| Documented history of a severe allergic reaction to any component of the study protocol | [S2] |
| Current enrollment in a conflicting interventional study | [S2] |
| Inability to provide informed consent independently | [S2] |
| Age outside the protocol‑specified range (confirmed with government ID) | [S2] |
| Recent major surgery within the preceding eight weeks | [S2] |
| Active immunosuppressive therapy **unless** the treating physician provides written clearance | [S2] |

These are the explicit exclusion conditions listed in the retrieved guidelines. No additional exclusion criteria are mentioned in the provided context.
```

</details>

---

### ⚠️ Which sample had the highest activation score?

`medical` · `431f3c656b95` · 11645 ms

Correct (TC-017, 0.91) — but *by luck*. The medical corpus is 6 rows and k=4, so top-k happened to include the winner. The identical question over 15 financial rows failed. Do not read this as evidence that superlatives work.

| stage | detail | ms |
|---|---|---|
| route | medical (explicit) | 0 |
| plan | 1 sub-query | 3070 |
| retrieve | 4 of 4 candidates | 98 |
| synthesize | 1 citation, 0 unresolved | 8477 |

<details><summary>Sources fused and answer</summary>

| # | id | rrf |
|---|---|---|
| S1 | `medical_tabular_medical_placeholder_3fc69d_0003` ←cited | 0.0323 |
| S2 | `medical_tabular_medical_placeholder_3fc69d_0001` | 0.0323 |
| S3 | `medical_tabular_medical_placeholder_3fc69d_0004` | 0.0315 |
| S4 | `medical_tabular_medical_placeholder_3fc69d_0000` | 0.0313 |

```
The sample with the highest activation score was **TC‑017**, which had an activation score of **0.91**【S1】.
```

</details>

---

### ✅ What are the exclusion criteria, and which samples showed strong antigen activation?

`medical` · `7ef933744d9f` · 19278 ms

**The architectural claim, demonstrated.** One answer citing both a DOCX chunk and a CSV row — the synthesis layer cannot tell which extractor produced which source, which is exactly what the shared KnowledgeUnit schema is for. Caveat: TC-014 (0.87, 'strong positive response') was ranked #4 by dense retrieval but dropped out of the hybrid top-4, because RRF favours documents both rankers agree on over one ranker's strong pick. Hybrid is not strictly better at this corpus size — which is what the Phase 6 retrieval ablation is for.

| stage | detail | ms |
|---|---|---|
| route | medical (explicit) | 0 |
| plan | 2 sub-queries (decomposed) | 4931 |
| retrieve | 8 of 8 candidates | 63 |
| synthesize | 4 citations, 0 unresolved | 14284 |

Sub-queries:
1. What are the exclusion criteria?
2. Which samples showed strong antigen activation?

<details><summary>Sources fused and answer</summary>

| # | id | rrf |
|---|---|---|
| S1 | `medical_textual_medical_guideline_placeholder_52f6a9_0000` ←cited | 0.0328 |
| S2 | `medical_tabular_medical_placeholder_3fc69d_0001` | 0.0328 |
| S3 | `medical_textual_medical_guideline_placeholder_52f6a9_0002` ←cited | 0.0323 |
| S4 | `medical_tabular_medical_placeholder_3fc69d_0005` | 0.0318 |
| S5 | `medical_textual_medical_guideline_placeholder_52f6a9_0001` | 0.0315 |
| S6 | `medical_tabular_medical_placeholder_3fc69d_0000` ←cited | 0.0315 |
| S7 | `medical_tabular_medical_placeholder_3fc69d_0004` | 0.0313 |
| S8 | `medical_tabular_medical_placeholder_3fc69d_0003` ←cited | 0.031 |

```
**Exclusion criteria (as defined in the protocol)**  
Candidates are excluded if they meet any of the following conditions:  

| Criterion | Source |
|-----------|--------|
| Active infection, uncontrolled chronic condition, or pregnancy | [S1] |
| Severe allergic reaction to any component of the study protocol | [S3] |
| Current enrollment in a conflicting interventional study | [S3] |
| Inability to provide informed consent independently | [S3] |
| Age outside the protocol‑specified range (verified with ID) | [S3] |
| Recent major surgery within the preceding eight weeks | [S3] |
| Active immunosuppressive therapy unless the treating physician provides written clearance | [S3] |

**Samples that showed strong antigen activation**  
The assay results that indicate a robust cellular response (activation score ≥ 0.8) are:

| Sample ID | Antigen panel | Activation score | Comment | Source |
|-----------|---------------|------------------|---------|--------|
| TC‑014 | Panel B | 0.87 | “Strong positive response” | [S6] |
| TC‑017 | Panel C | 0.91 | “Sustained high activation” | [S8] |

These two samples demonstrated the highest activation scores and were noted as strong antigen‑activated responses in the study records.
```

</details>

---

### ✅ What was the activation score for TC-014?

`medical` · `51e195282828` · 7684 ms

Exact-ID lookup, the case BM25 exists for. This one only works because of the Unicode fix: the narrative generator writes 'TC-014' with U+2011 (non-breaking hyphen), so before normalization a user typing an ordinary hyphen scored 0.0000 against every document.

| stage | detail | ms |
|---|---|---|
| route | medical (explicit) | 0 |
| plan | 1 sub-query | 4183 |
| retrieve | 4 of 4 candidates | 667 |
| synthesize | 1 citation, 0 unresolved | 2835 |

<details><summary>Sources fused and answer</summary>

| # | id | rrf |
|---|---|---|
| S1 | `medical_tabular_medical_placeholder_3fc69d_0000` ←cited | 0.0328 |
| S2 | `medical_tabular_medical_placeholder_3fc69d_0002` | 0.032 |
| S3 | `medical_tabular_medical_placeholder_3fc69d_0005` | 0.0318 |
| S4 | `medical_tabular_medical_placeholder_3fc69d_0003` | 0.0313 |

```
The activation score for sample **TC‑014** was **0.87**【S1】.
```

</details>

---

### ✅ How should vital signs be recorded during screening?

`medical` · `e91beb8161b7` · 10628 ms

Procedural prose from the DOCX, 2 resolved citations.

| stage | detail | ms |
|---|---|---|
| route | medical (explicit) | 0 |
| plan | 1 sub-query | 2140 |
| retrieve | 4 of 4 candidates | 58 |
| synthesize | 2 citations, 0 unresolved | 8429 |

<details><summary>Sources fused and answer</summary>

| # | id | rrf |
|---|---|---|
| S1 | `medical_textual_medical_guideline_placeholder_52f6a9_0000` ←cited | 0.0328 |
| S2 | `medical_textual_medical_guideline_placeholder_52f6a9_0003` ←cited | 0.0317 |
| S3 | `medical_tabular_medical_placeholder_3fc69d_0004` | 0.0313 |
| S4 | `medical_textual_medical_guideline_placeholder_52f6a9_0002` | 0.0312 |

```
Vital signs are captured at the initial screening interview and entered immediately into the electronic case‑report form (eCRF).  
- The screening staff record the baseline heart rate, blood pressure, and body temperature **at the time of observation** and cross‑check these values against the study’s exclusion criteria (e.g., active infection, uncontrolled chronic disease, pregnancy) before proceeding with enrollment [S1].  
- All measurements are entered directly into the eCRF; retrospective transcription from paper notes is discouraged unless unavoidable, and any blank field must carry an explicit reason code rather than being left ambiguous [S2].  
- The time of each vital‑sign measurement is logged in the site’s local time zone with the offset explicitly noted to avoid discrepancies across multi‑site sites [S2].  

Thus, vital signs should be recorded in real time, entered directly into the eCRF, and time‑stamped with local time‑zone information, ensuring traceability and compliance with the study’s data‑quality standards.
```

</details>

---

### ✅ What is the recommended dosage of ibuprofen for these subjects?

`medical` · `409cd86eb067` · 19758 ms

**Correct abstention**, and a harder one than the TCS case: plausible, in-domain, and adjacent to real content. The planner expanded to 4 sub-queries hunting for it, found nothing, and said so.

| stage | detail | ms |
|---|---|---|
| route | medical (explicit) | 0 |
| plan | 4 sub-queries (decomposed) | 3476 |
| retrieve | 6 of 6 candidates | 122 |
| synthesize | 0 citations, 0 unresolved | 16160 |

Sub-queries:
1. What is the recommended dosage of ibuprofen for adults?
2. What is the recommended dosage of ibuprofen for children?
3. What is the recommended dosage of ibuprofen for pregnant women?
4. What is the recommended dosage of ibuprofen for elderly patients?

<details><summary>Sources fused and answer</summary>

| # | id | rrf |
|---|---|---|
| S1 | `medical_tabular_medical_placeholder_3fc69d_0005` | 0.0318 |
| S2 | `medical_textual_medical_guideline_placeholder_52f6a9_0002` | 0.0315 |
| S3 | `medical_tabular_medical_placeholder_3fc69d_0000` | 0.0315 |
| S4 | `medical_textual_medical_guideline_placeholder_52f6a9_0004` | 0.0313 |
| S5 | `medical_textual_medical_guideline_placeholder_52f6a9_0003` | 0.0312 |
| S6 | `medical_textual_medical_guideline_placeholder_52f6a9_0001` | 0.0311 |

```
The retrieved context does not contain any information about ibuprofen or its recommended dosage for the subjects. No dosage details are provided in the available excerpts.
```

</details>

---
