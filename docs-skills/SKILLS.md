# SKILLS.md — Capability Registry

Each skill is a discrete, independently testable capability with its own contract, prompt strategy, failure mode, and evaluation hook. The agent is a composition of these, not a monolithic prompt.

**Why decompose at all.** A single prompt that classifies, drafts, and routes is shorter to write and impossible to debug: when the output is wrong you can't tell which sub-decision failed, and you can't measure any stage independently. Decomposition costs latency and tokens and buys attributable failure. For an assignment graded on proof, that trade is obvious.

---

## S1 — Guard (deterministic)

| | |
|---|---|
| **Purpose** | Apply hard rules and redact PII before any model sees the message |
| **Input** | `raw_text`, `author_id`, `thread_history` |
| **Output** | `{fired: bool, rule_id, redacted_text, sensitive: bool}` |
| **Method** | Curated keyword/regex sets per rule (HR-1..HR-8), plus a repeat-contact lookup |
| **Model?** | No — deliberately. Safety that depends on a model inherits the model's failures |
| **Primary failure mode** | Keyword brittleness. "I want my money back" ≠ "refund" |
| **Mitigation** | Paraphrase lists seeded from real dataset examples, not imagination; model-based routing acts as a second net for anything missed |
| **Eval hook** | Rule-level recall measured against golden-set escalation labels; each rule's individual fire-rate and precision reported |

## S2 — Intent classification

| | |
|---|---|
| **Purpose** | Assign one of ~8 brand-derived intents, or `other` |
| **Input** | `clean_text` |
| **Output** | `{intent, confidence, rationale}` |
| **Method** | LLM, temp 0, structured JSON output. Prompt = taxonomy definitions + boundary rules + k few-shot examples from the **dev split only** |
| **Key design choice** | Definitions include explicit boundary cases ("a failed charge is `billing`; removing a family member is `plan_management`"). Most classifier errors in a small taxonomy are boundary errors, not wild misses |
| **Confidence** | Self-reported by the model, which is **weakly calibrated** — treated as a rough gate at 0.55, never reported as a probability. A calibration curve on the dev split is included precisely to show how unreliable it is |
| **Primary failure mode** | Multi-intent tweets; sarcasm; `other` acting as a dumping ground |
| **Eval hook** | Macro-F1, per-class F1, confusion matrix, calibration plot, `other`-rate |

## S3 — Evidence retrieval

| | |
|---|---|
| **Purpose** | Find historical (customer, brand reply) pairs that ground the draft |
| **Input** | `clean_text`, `predicted_intent` |
| **Output** | `list[{pair_id, customer_msg, brand_reply, score}]` |
| **Method** | MiniLM embeddings, cosine top-k=5, filtered to predicted intent and `score ≥ 0.35`, substantive replies only |
| **Key design choice** | Intent-filtering raises precision but couples S3 to S2's correctness. The coupling is measured, not assumed away: hit-rate is reported separately for correctly and incorrectly classified messages |
| **Primary failure mode** | Topically similar, differently resolved. Two "song won't play" tweets may have had opposite root causes, so confident wrong steps get grounded in real evidence |
| **Mitigation** | `min_evidence_above_floor = 2` — one similar case is an anecdote |
| **Eval hook** | Hit-rate (≥1 retrieved pair shares gold intent); score distribution; manual review of the lowest-scoring accepted retrievals |

## S4 — Reply generation

| | |
|---|---|
| **Purpose** | Draft a brand-voice reply grounded in retrieved evidence |
| **Input** | `clean_text`, `evidence[]`, `voice_spec` |
| **Output** | `draft_reply` (string, ≤280 chars) |
| **Method** | LLM, temp 0.3. Prompt = evidence pairs verbatim + voice spec derived from corpus statistics (median length, contraction rate, sign-off pattern, emoji rate) + the forbidden-content list from `AGENT_POLICY.md` §4 |
| **Key design choice** | The voice spec is **measured from the data**, not described from intuition. "Sound friendly" is unfalsifiable; "median 140 chars, signs off with a first initial, uses an emoji in 30% of replies" is checkable |
| **Primary failure mode** | Confident specificity — inventing a settings path that appears in no evidence |
| **Mitigation** | S5 validator; groundedness rubric dimension |
| **Eval hook** | Judge rubric (groundedness, relevance, actionability, tone, safety); length distribution vs real replies; hallucinated-entity rate |

## S5 — Output validation (deterministic)

| | |
|---|---|
| **Purpose** | Make the safety guarantee auditable rather than aspirational |
| **Input** | `draft_reply`, `evidence[]` |
| **Output** | `{ok, violations[]}` |
| **Checks** | URLs not present in evidence; currency amounts; digit runs resembling PII; length bounds; refund/timeline promise phrases; password/OTP requests |
| **Model?** | No. A regex can be tested exhaustively; a model cannot |
| **On failure** | Force escalate, `trigger: policy_violation`, retain the rejected draft for failure analysis |
| **Eval hook** | Violation rate per system — this is where B2 (no retrieval) is expected to look worst, which is itself the argument for retrieval |

## S6 — Routing

| | |
|---|---|
| **Purpose** | Final auto-handle vs escalate decision with a stated reason |
| **Input** | guard result, intent+confidence, evidence count, validation result, draft |
| **Output** | `{route, route_reason, trigger}` |
| **Method** | Hybrid. Rules resolve first and are non-overridable; the LLM judges only the residue |
| **Key design choice** | Tuned for **recall on escalate**. Precision is reported honestly and not optimised, because the error costs are asymmetric by roughly two orders of magnitude |
| **Primary failure mode** | Profanity treated as severity. An angry-but-trivial tweet escalates; a calm "I've lost 400 playlists" may not |
| **Eval hook** | Escalation P/R/F1 with bootstrap CI; confusion matrix; breakdown of decisions by `trigger` so rule-driven and model-driven escalations are never conflated |

## S7 — LLM judge (evaluation-only, not in the agent path)

| | |
|---|---|
| **Purpose** | Score reply quality at a scale hand-scoring can't reach |
| **Input** | customer message, draft reply, evidence |
| **Output** | `{groundedness, relevance, actionability, tone_match, safety}` each 1–5 + rationale |
| **Method** | One dimension per call, temp 0, blind to system identity, system order shuffled per item |
| **Status** | **An instrument under test, not a source of truth.** Validated against 60 human-scored replies; any dimension with weighted κ < 0.4 is excluded from headline claims |
| **Primary failure mode** | Self-preference — the judge shares a model family with the generator and may reward its own style |
| **Mitigation** | Blinding, shuffling, human agreement measurement, and a candidate cross-family judge if time allows |
| **Eval hook** | Weighted Cohen's κ and Spearman per dimension; self-consistency across two runs; disagreement cases read manually and quoted in the report |

---

## Composition map

| System | S1 | S2 | S3 | S4 | S5 | S6 |
|---|---|---|---|---|---|---|
| **B0 trivial** | — | majority class | — | fixed canned reply | — | always-auto / always-escalate |
| **B1 simple** | keyword only | TF-IDF + LogReg | ✓ | nearest reply copied verbatim | ✓ | keyword rules |
| **B2 LLM-only** | ✓ | ✓ | — | zero-shot, no evidence | ✓ | ✓ |
| **Full agent** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Reading down the columns gives the ablation: **B2 vs Full isolates retrieval's contribution**, and **B1 vs Full isolates the LLM's contribution over classical NLP**. Each baseline exists to answer one specific question, not to lose gracefully.

## Skills deliberately not built

| Not built | Why | What it would have bought |
|---|---|---|
| Sentiment / urgency scoring | Overlaps routing without adding an independent signal at this data scale | Possibly better severity detection on calm-but-severe messages |
| Conversation summarisation | Single-turn scope | Better repeat-contact handling than HR-5's crude counter |
| Multi-lingual handling | English-only scope; can't evaluate what I can't read | Coverage of non-English traffic, currently escalated wholesale |
| Reply reranking (generate N, pick best) | Cost, and it needs a trusted scorer — but the scorer is the thing under test | Likely a real quality gain; first item on the one-more-week list |
| Knowledge-base grounding | No KB in the dataset; only past replies exist | Freshness, which past replies from 2017 cannot provide |
