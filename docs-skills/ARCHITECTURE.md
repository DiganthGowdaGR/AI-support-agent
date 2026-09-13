# ARCHITECTURE.md — System Design

**One line:** an offline batch pipeline builds a grounded retrieval corpus from raw tweets; a four-stage agent turns one inbound message into a triage decision; an evaluation harness scores it from cache.

Three subsystems, deliberately decoupled so the eval harness can run with zero API calls:

```
  ┌────────────────┐      ┌────────────────┐      ┌────────────────┐
  │ A. DATA        │─────▶│ B. AGENT       │─────▶│ C. EVALUATION  │
  │ (offline, once)│      │ (per message)  │      │ (from cache)   │
  └────────────────┘      └────────────────┘      └────────────────┘
```

---

## A. Data subsystem (offline, run once, output committed)

```
twcs.csv (~3M rows)
   │  filter to brand handle + their interlocutors
   ▼
brand_tweets
   │  thread reconstruction: in_response_to_tweet_id ──▶ tweet_id
   │  concatenate multi-tweet brand replies in timestamp order
   ▼
threads
   │  clean: strip @handles, URL ──▶ <url>, collapse whitespace,
   │         langdetect==en, near-dupe removal (MinHash)
   ▼
pairs  (customer_msg, brand_reply, ids, timestamp)
   │  deflection filter  ─────────────▶ discarded (but counted)
   ▼
corpus.parquet  +  embeddings.npy  +  drop_report.json
```

**Design notes**

- **Thread reconstruction is the sneaky-hard part.** Parents are frequently missing from the dump, brands split replies across tweets, and customers reply to themselves. The joiner handles each case explicitly and the drop report accounts for every lost row. Silent row loss is how eval sets quietly become unrepresentative.
- **The deflection filter is load-bearing.** Replies that are pure "DM us" carry no groundable content. They are excluded from the retrieval corpus but *counted*, because the deflection rate is the statistic that justified the brand choice.
- **Near-dupe removal before sampling**, so the golden set isn't 15 copies of the same complaint.
- **Everything is seeded.** `SEED=42` in config; two runs produce byte-identical parquet.

**Storage:** parquet for tabular, numpy memmap for embeddings, flat JSON for reports. No database — a database here is complexity with no evaluative payoff.

---

## B. Agent subsystem (per message)

```
                     inbound tweet
                          │
                 ┌────────▼────────┐
                 │ 0. GUARD        │  hard rules HR-1..HR-8, PII redaction,
                 │    (deterministic)│  language check
                 └────────┬────────┘
                 fires ───┴─── passes
                   │            │
         escalate, no draft     ▼
                        ┌───────────────┐
                        │ 1. CLASSIFY   │  LLM + taxonomy defs + few-shot
                        └───────┬───────┘  → intent, confidence
                    conf < floor│
                   ┌────────────┴────┐
             escalate              ▼
                          ┌───────────────┐
                          │ 2. RETRIEVE   │  embed → cosine top-k
                          └───────┬───────┘  filtered by intent + sim floor
                  < min_evidence  │
                   ┌──────────────┴──┐
             escalate             ▼
                          ┌───────────────┐
                          │ 3. GENERATE   │  evidence + voice spec → draft
                          └───────┬───────┘
                                  ▼
                          ┌───────────────┐
                          │ 4. VALIDATE   │  deterministic content checks
                          └───────┬───────┘
                        fails ────┴──── passes
                          │              ▼
                    escalate      ┌───────────────┐
                                  │ 5. ROUTE      │  model judgement
                                  └───────┬───────┘
                                          ▼
                                   AgentOutput JSON
```

**Why guard-first.** Hard rules run before any model call: they're cheaper, deterministic, and — critically — they cannot be talked out of a decision by a persuasive message. Putting safety behind a model call means safety inherits the model's failure modes.

**Why retrieval is intent-filtered.** Retrieving within the predicted intent raises precision but couples two stages: a misclassification poisons the evidence. This is a real coupling risk and the eval measures it directly (retrieval hit-rate conditioned on correct vs incorrect classification).

**Why a deterministic validator after a model.** The prompt is the primary defence against hallucinated URLs and invented prices; the validator is the backstop that makes the guarantee auditable. "The model was told not to" is not a control. A regex is.

**Module contracts** (`src/`):

| Module | In | Out | Deterministic? |
|---|---|---|---|
| `guard.py` | raw text, thread history | `GuardResult{fired, rule_id, redacted_text}` | yes |
| `classify.py` | clean text | `{intent, confidence}` | no (cached) |
| `retrieve.py` | text, intent | `list[EvidencePair]` + scores | yes given embeddings |
| `generate.py` | text, evidence, voice spec | `draft_reply` | no (cached) |
| `validate.py` | draft, evidence | `{ok, violations[]}` | yes |
| `route.py` | all of the above | `{route, reason, trigger}` | partly |
| `agent.py` | tweet | `AgentOutput` | — |

Each module is independently callable and independently testable. The baselines swap modules rather than reimplementing the pipeline: B1 = `classify_tfidf` + `retrieve` + `copy_nearest`; B2 = `classify` + `generate_no_evidence`.

---

## C. Evaluation subsystem

```
golden_v1.jsonl ──┐
                  ├──▶ runner ──▶ cached_predictions/{system}.jsonl
systems {B0,B1,   │                        │
        B2,full}──┘                        ▼
                                  ┌─────────────────┐
                                  │ metrics.py      │ macro-F1, per-class F1,
                                  │                 │ escalation P/R, hit-rate,
                                  │                 │ bootstrap 95% CI
                                  └────────┬────────┘
                                  ┌────────▼────────┐
                                  │ judge.py        │ 5-dim rubric, blind,
                                  │                 │ shuffled, temp 0
                                  └────────┬────────┘
                                  ┌────────▼────────┐
                                  │ judge_validation│ human scores (n=60)
                                  │                 │ → weighted κ, Spearman
                                  └────────┬────────┘
                                           ▼
                                  results.md + figures/
```

**The cache is the architecture's most important feature.** Every LLM call is keyed by `sha256(model + prompt + params)` and written to `outputs/cache/`. Committing the cache means `make eval` reproduces every headline number offline in well under 15 minutes with no API key — which is exactly what the brief asks for. It also means results can't silently drift between the report being written and a grader running the code.

The honest cost: a cached result is a *snapshot*, not a re-derivation. A grader running `make agent` with their own key may get slightly different generations. The README states this explicitly rather than implying the numbers are model-independent.

---

## Tech choices

| Choice | Alternative rejected | Why |
|---|---|---|
| Parquet + numpy | SQLite / vector DB | ~10k vectors; brute-force cosine is milliseconds. A vector DB is infrastructure theatre at this scale. |
| Sentence-transformers (`all-MiniLM-L6-v2`) local | Hosted embedding API | Free, offline, reproducible, fast enough. Embedding quality is not the bottleneck here. |
| Hosted LLM for classify/generate/judge | Local open model | Quality per unit of my time; cache makes reproducibility a non-issue |
| TF-IDF + LogReg for B1 | Fine-tuned small transformer | B1's job is to be a *fair, cheap* bar, not to win |
| Makefile + CLI | Notebook-driven | Notebooks aren't reproducible; notebooks are kept for exploration only |
| JSONL everywhere | Pickle | Human-readable, diffable, greppable during failure analysis |

## Data flow guarantees

1. **No test-split leakage.** Few-shot examples are drawn only from the dev split; the retrieval corpus excludes every tweet appearing in the golden set. Enforced by an assertion in `build_dataset.py`, not by discipline.
2. **Seeded end to end.** Sampling, clustering, bootstrap, and judge shuffling all take the same seed.
3. **Append-only cache.** Cache entries are never overwritten; a changed prompt produces a new key, so old results stay auditable.
4. **One-way test gate.** `run_eval.py --split test` refuses to run unless `outputs/dev_frozen.lock` exists, which is written when dev-split iteration ends. Structural enforcement of "score the test set once."
