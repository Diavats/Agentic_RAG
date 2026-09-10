# Progress log — plain English

What has been built, what broke, and how to check any of it yourself.

Written for someone who wants to *verify* the work, not take it on trust.
Yes — the terminal is where you check everything. Every command below runs in
VSCode's built-in terminal (`` Ctrl+` ``).

---

## 1. The 30-second version

The project started as a **terminal-only script** that answered questions about
one spreadsheet. It is now a **two-domain retrieval system** with a test suite.

| Then | Now |
|---|---|
| One hardcoded collection | Two separate collections: `medical`, `financial` |
| Spreadsheets only | Spreadsheets **and** Word documents, same pipeline |
| Extractors written but never connected to anything | Wired end to end |
| Answer = a string | Answer = a full record of every decision made |
| You had to say which domain to search | The system works it out itself |
| No version control | Git repo, pushed to GitHub after every phase |
| No tests | 135 tests |

---

## 2. What changed in each file, and why

### Bugs fixed before building anything new

These were found by reading the code. All four could destroy data **silently** —
no crash, no error message, just wrong results.

| File | What was wrong | Why it mattered |
|---|---|---|
| `src/build_index.py` | The keyword (BM25) index was rebuilt from scratch on every ingest and overwrote the old file | Ingesting a second batch **deleted the first batch** from keyword search. Medical data arrives in pieces, so this was the normal path. Searches still returned results, so nobody would notice |
| `src/extractors/*.py` | Both extractors numbered items from 0 **per file** | Two medical CSVs both produced an item called `medical_tabular_0000`. The database overwrites by name, so **the second file silently erased the first** |
| `src/extractors/text_extractor.py` | Documents were cut into 500-token chunks, but the embedding model only reads 256 | **The back half of every chunk was invisible to search.** No warning is printed — the library just truncates |
| `src/extractors/text_extractor.py` | Chunks were rebuilt using `tokenizer.decode()` | That lowercases everything and mangles punctuation: `Dr. Smith reported 5.2%` came back as `dr. smith reported 5. 2 %`. That text is what a viva panel would see quoted as a source |

### New capability

| File | What it does |
|---|---|
| `src/unit_store.py` **(new)** | Saves extracted content to disk so it is never re-extracted. Extraction costs one AI API call per spreadsheet row, so redoing it wastes real quota |
| `src/trace.py` **(new)** | Records what the system did for each question: which domain, how it split the question, what it found, what it cited, how long each step took |
| `src/build_index.py` | Now accepts the shared data format both extractors produce, and cleans spreadsheet values the database would reject |
| `src/main.py` | New commands: `setup`, `ingest --domain`, `index --domain`, `ask --domain` |
| `src/agent.py` | Returns the full record instead of just an answer string |
| `tests/` **(new)** | 135 tests. Every one is a trap for a bug that actually happened |

---

## 3. Errors hit along the way

Every one of these was found by *running* the code, not by reading it.

### 3.1 Answer printing crashed on Windows — **FIXED**

- **What you saw:** `UnicodeEncodeError: 'charmap' codec can't encode character`
- **Root cause:** Windows terminals default to an old encoding (cp1252). The AI
  writes typographic characters — curly quotes, em dashes — constantly. A
  perfectly good answer crashed on the way to the screen.
- **Fix:** `src/main.py` forces UTF-8 output at startup.

### 3.2 Keyword search was completely dead — **FIXED**

- **What you saw:** nothing. That is the problem.
- **Root cause:** the AI writes sample IDs like `TC‑014` using a *non-breaking
  hyphen*. A user types `TC-014` with a normal one. Different characters, so
  the search scored **0.0000 against every document in the database**. Keyword
  search — the whole reason that half of the system exists — contributed
  nothing, and results still looked normal because the other half covered for it.
- **How nearly it was missed:** the obvious test *passed*. With every score at
  zero, sorting returns the original order, and the target document happened to
  be first. The test only failed once it checked the **scores** instead of
  whether the document appeared.
- **Fix:** `src/build_index.py` converts typographic characters to plain ones,
  the same way for both stored text and typed queries.

### 3.3 A third of all citations were being thrown away — **FIXED**

- **Root cause:** the system asks the AI to cite sources as `[S1]`. On 3 of the
  first 10 questions it used fullwidth brackets instead — `【S1】`. The code that
  reads citations only understood square brackets, so it recorded **zero
  citations** for those answers.
- **Why it mattered:** citation accuracy is one of the project's headline
  scores. Left alone, the evaluation would have reported it about **30 points
  too low** — and the number would have looked believable.
- **Fix:** `src/trace.py` now reads what the AI actually writes.

### 3.4 The test suite hung — **FIXED**

- **What you saw:** tests ran for 10+ minutes with no output.
- **Root cause:** `build_index()` loaded a fresh copy of the embedding model on
  **every call** — about 20 seconds each. This was invisible in normal use
  (once per run) but the tests call it dozens of times. It also meant two
  copies of the same model sat in memory, which matters on a small server.
- **Fix:** `src/build_index.py` reuses the copy the search layer already holds.

### 3.5 Blank dates were stored as the word "NaT" — **FIXED**

- **Root cause:** pandas' "missing date" value is *technically* a date, so the
  code that formats dates accepted it and wrote the literal text `NaT`.
- **Why it mattered:** a blank cell in a spreadsheet would appear in the
  database as real-looking data.
- **Fix:** `src/build_index.py` checks for it explicitly.

### 3.6 One test was wrong, not the code — **FIXED (the test)**

- A test built a 2-document database and expected a keyword search to score
  above zero. It scored exactly zero.
- **Root cause:** BM25's relevance formula is `log(N − freq + 0.5) − log(freq +
  0.5)`. With a word in 1 of 2 documents that is `log(1.5) − log(1.5)` = **0**.
  Measured: the same word scores 0.00 at 2 documents, 0.51 at 3, 1.95 at 11.
- **Worth knowing:** keyword search needs a handful of documents before it does
  anything useful. At the real corpus size (11 and 15) it is fine.
- **Fix:** the test now uses a realistic corpus.

---

## 4. Known problems NOT fixed (on purpose)

Honesty is worth more than a clean-looking list.

| Problem | Why it is not fixed |
|---|---|
| **"Which stock grew most?" gives the wrong answer.** It says SHAREINDIA (71.79%); the real answer is DIACABS (1003.70%) | This is a structural limit of retrieval systems. Answering "which is the most X" needs reading *every* row; retrieval only fetches the few that look most similar to the question. Documented in `docs/TRACES.md` |
| Combining both search methods can drop a document that one method ranked highly | The fusion method deliberately prefers documents both methods agree on. Whether that helps here is exactly what the planned evaluation measures |
| 4 of 10 questions take longer than the 8-second target | The delay is the AI provider's response time, not our code. Retrieval is under 200ms |

---

## 5. How to check all of this yourself

Open VSCode's terminal (`` Ctrl+` ``) in the project folder. Run these in order.

### Step 0 — build the indexes (first time, or after a fresh clone)

```bash
venv/Scripts/python.exe -m src.main setup
```

Zero API calls. The search index is **not** in version control, because Chroma
writes to its files whenever you *read* — one query dirtied three binary files,
so every question produced a spurious change. What is committed is
`data/generated/*_units.json`: plain text, diffs cleanly, and it holds the
expensive part (one AI call per spreadsheet row). The index rebuilds from it in
a couple of seconds.

### Step 1 — confirm you are looking at the same files

```bash
git log --oneline
```

Expect a list of commits, newest first, ending with `Initial commit`.

### Step 2 — run the tests

```bash
venv/Scripts/python.exe -m pytest
```

Takes about two minutes (it loads the embedding model once). Expect
`132 passed, 3 skipped`. The 3 skipped ones cost API quota — see step 6.

### Step 3 — see the two domains

```bash
venv/Scripts/python.exe -c "import chromadb; c=chromadb.PersistentClient(path='chroma_store'); [print(f'{x.name}: {c.get_collection(x.name).count()} documents') for x in c.list_collections()]"
```

Expect `financial: 15` and `medical: 11`.

### Step 4 — ask a question

```bash
venv/Scripts/python.exe -m src.main ask --domain medical --question "What are the exclusion criteria?"
```

You will see the domain, how the question was split, which sources were found
with their scores, the answer with `[S1]`-style citations, and timings.

### Step 5 — prove format-agnosticism (the core claim)

```bash
venv/Scripts/python.exe -m src.main ask --domain medical --question "What are the exclusion criteria, and which samples showed strong antigen activation?"
```

One answer citing **both** a Word document and a spreadsheet row. The system
cannot tell them apart — that is the point of the shared format.

### Step 6 — optional, uses API quota

```bash
venv/Scripts/python.exe -m pytest -m live
```

### Step 7 — read the failures

Open `docs/TRACES.md` in VSCode. Ten real runs, including the wrong answer.

---

## 6. Where to look in VSCode

| Panel | What you will see |
|---|---|
| **Explorer** | `src/` code · `tests/` tests · `docs/` these documents |
| **Source Control** | Every commit. Click one to see exactly what changed |
| **Terminal** | Where you run everything above |
| `docs/TRACES.md` | Real question runs, passes and failures |
| `docs/PROGRESS.md` | This file |

One setting worth turning on: **File → Auto Save**. If a file sits open with
unsaved edits while work happens on disk, pressing Ctrl+S can overwrite it.
