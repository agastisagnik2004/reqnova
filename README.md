<p align="center"><img src="frontend/assets/reqnova-logo.png" alt="Reqnova - AI for Requirements" width="300" /></p>

# Reqnova: AI for Requirements

> Messy customer conversation → grounded, structured software requirements, **without inventing anything**.

**Reqnova** is a multi-step AI system that turns vague, conversational customer descriptions (typed text, PDFs, Word files or **photos of notes and tables**) into a structured requirements draft. Every requirement cites the customer sentence it came from. Anything the customer didn't say becomes **missing information**, a **clarifying question** or a clearly labelled **assumption**, never a made-up requirement.

---

## The problem

Customers describe software the way people talk: incompletely and informally.

> "We need an employee attendance system. Employees should be able to check in from their phones. Managers should see who is absent. HR should be able to download reports. Sometimes people forget to check out…"

Reqnova produces a **problem statement, actors, functional & non-functional requirements, user stories, acceptance criteria, missing information, clarifying questions and edge cases**, under one hard rule:

> **Never invent requirements.**
> ✗ "The system should support biometric authentication."
> ✓ *Missing information: Authentication method has not been specified.*

Generating a spec is easy; any model writes a convincing one. The hard part is **knowing which parts are grounded**. Reqnova therefore separates extraction from design, makes every claim **traceable** to the input, and treats **gaps as first-class output**.

## How it works

```
Input (text / PDF / DOCX / image)
  └─► Vision model for images & scans ─► text the analyst can review
        └─► Prepare (code): number sentences S1..Sn, injection & length checks
              └─► 1 Gate (reasoning): is this a software requirement?  ── no ─► rejected, nothing fabricated
                    └─► 2 Extract (reasoning): actors, needs + exact quotes, vague terms, contradictions
                          └─► quote & citation check (code)
                                ├─► 3a Transform (reasoning): problem, actors, FR, NFR, stories, acceptance criteria
                                └─► 3b Ambiguity (reasoning): missing info, questions, edge cases, assumptions  (parallel)
                                      └─► grounding rules (code): fake IDs, watch-list terms, invented numbers
                                            └─► 4 Verify (reasoning, as auditor): supported / partial / unsupported
                                                  └─► assemble (code): unsupported → assumptions, quality KPIs
```

| Idea | How |
|---|---|
| **Traceability** | Every item carries `source_ids` (e.g. `S2`). Hovering a citation highlights the original sentence. |
| **Honest labels** | Requirements are `stated`, `implied` or `assumption`, and `supported`, `partial` or `unsupported`. |
| **`[TBD]`, not defaults** | Unknown values (time limits, formats, channels) become visible placeholders. |
| **Code as referee** | Deterministic checks for invalid citations, unquoted facts, a hallucination watch-list and invented numbers. |
| **Gaps as output** | A dedicated ambiguity step, separate from writing requirements. |
| **Robust structure** | Pydantic schemas, JSON self-repair, rate-limit backoff, a fallback chain and deadlines. |

Full design, diagram and trade-offs: **[ARCHITECTURE.md](ARCHITECTURE.md)**

## Features

* Paste text or upload **PDF / DOCX / TXT / images** (tables are preserved)
* Live pipeline progress with per-step status
* Two selectable reasoning models: **Model_1** (fast, default) and **Model_2** (deep)
* Badges for origin and verification, plus citation chips linked to the source sentences
* **History** tab: every analysis is saved; search, reopen and delete
* Export to **Markdown** or **JSON**
* **Light / dark / system** theme

## Run it locally

**Requirements:** Python 3.10+, and API access to an OpenAI-compatible endpoint that serves one or two reasoning models and a vision model.

```bash
git clone https://github.com/agastisagnik2004/reqnova.git
cd reqnova
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env            # macOS/Linux: cp .env.example .env
# edit .env: endpoint, model IDs and API keys

python -m uvicorn app.main:app --port 8765
```

Open **http://localhost:8765**, pick a sample or paste text, and press **Analyse requirements**.

### Configuration (`.env`)

| Variable | Meaning |
|---|---|
| `API_BASE_URL` | OpenAI-compatible endpoint |
| `MODEL_1`, `MODEL_1_API_KEY` | Fast reasoning model (default) |
| `MODEL_2`, `MODEL_2_API_KEY` | Deep reasoning model |
| `BACKUP_MODEL` | Optional last-resort reasoning model |
| `VISION_MODEL`, `VISION_FALLBACK_MODEL`, `VISION_API_KEY` | Vision model for images and scanned PDFs |

Model IDs never appear in the UI, API responses or history; only `Model_1` / `Model_2` are shown.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/extract` | multipart file → `{text, method, pages, warnings}` |
| `POST` | `/api/analyze` | `{text, mode: "fast" \| "quality"}` → Server-Sent Events (`step` …, then `result`) |
| `POST` | `/api/export/markdown` | result JSON → Markdown spec |
| `GET` | `/api/history` | previous analyses, newest first |
| `GET` / `DELETE` | `/api/history/{id}` | reopen / delete one analysis |
| `DELETE` | `/api/history` | clear all history |
| `GET` | `/api/health` | configuration check |

## Project structure

```
app/
  config.py       settings from .env
  parser.py       file → text (vision model for images/scans)
  preprocess.py   sentence numbering, injection & length checks
  prompts.py      pipeline prompts + shared grounding rules
  llm.py          model client: JSON repair, backoff, fallback, deadlines
  schemas.py      Pydantic contracts
  grounding.py    rule-based hallucination guards
  pipeline.py     multi-step orchestrator
  history.py      saved analyses (SQLite)
  report.py       Markdown export
  main.py         HTTP API + SSE
  samples.json    sample inputs shown in the UI
frontend/         index.html, styles.css, app.js, assets/
ARCHITECTURE.md   design, diagram, decisions
```

## Team

| Name | Role |
|---|---|
| Sagnik Agasti | |

## Security

API keys live only in `.env`, which is git-ignored. Never commit `.env`.
