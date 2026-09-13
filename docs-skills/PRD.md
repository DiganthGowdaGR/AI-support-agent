# PRD — Twitter Support Agent (Hiver Take-Home)

**Version:** 1.0 · **Status:** pre-build · **Owner:** [you]
**Companion docs:** `plan.md` (execution plan), `DECISIONS.md` (decision log), `report.md` (findings)

> This PRD is written **before** building. Targets in §7 are pre-registered. If the system misses them, the report states the miss rather than moving the target. Metric-moving after seeing results is the failure mode this doc exists to prevent.

---

## 1. Problem

Support teams handling public social channels face high volume, high noise, and asymmetric risk: a wrong auto-reply to a paying customer is public and costly, while a slow reply to a trivial question is merely annoying. The bottleneck is triage — deciding what a message is about, what a good reply looks like, and whether a human needs to touch it at all.

This product is a **triage and drafting assistant** for one brand's Twitter support inbox. It does not replace the agent. It proposes.

## 2. Users

| User | Need | How they judge it |
|---|---|---|
| **Support agent** (primary) | A pre-classified queue and a draft they can send in one edit | "Did the draft save me time, or did I rewrite it?" |
| **Support lead** (secondary) | Confidence that risky tickets never auto-send | "How many escalations did it miss?" |
| **Evaluator (Hiver)** | Evidence the system is trustworthy | "Do I believe the headline number?" |

The third user is the one being optimised for in this take-home. Design choices that improve measurability beat choices that improve raw performance.

## 3. Scope

### In scope
- Single inbound customer tweet → intent, draft reply, routing decision with reason.
- One brand (see `plan.md` §0 for the selection gate).
- Retrieval grounded in that brand's historical replies.
- An evaluation harness with a validated LLM judge.

### Out of scope (deliberate)
| Excluded | Why | Cost of excluding |
|---|---|---|
| Multi-turn conversation state | Doubles surface area; single-turn is where triage decisions are actually made | Loses context on follow-ups; escalation on "still broken" is harder |
| Live Twitter/X integration | No evaluative value | None for this assignment |
| UI / deployment | Graders run a CLI | None |
| Fine-tuning | Time budget; retrieval is the cheaper lever to test | Untested whether tuning would close the gap |
| Sending replies autonomously | Human-in-the-loop by design | Product is assistive, not autonomous — stated as a product stance, not a limitation |
| Multi-label intents | Simplifies metrics | Multi-intent tweets get one label; measured in §8 as a known failure mode |

## 4. Functional requirements

### FR-1 — Intent classification
The system MUST assign exactly one intent from a closed taxonomy of ~8 brand-specific classes plus `other`, derived from the data (not borrowed from Banking77 or any generic list). It MUST return a confidence score. It MUST return `other` rather than force-fit an ambiguous message.

### FR-2 — Grounded reply drafting
The system MUST retrieve k similar historical *(customer message, brand reply)* pairs and generate a draft conditioned on them. The draft MUST:
- Return the IDs of the evidence used (`evidence_ids`), so every claim is auditable.
- Never invent URLs, prices, promo codes, dates, or policy not present in the evidence.
- Match brand voice and length distribution of real replies.
- Never promise a refund, credit, or specific resolution timeline.

### FR-3 — Routing
The system MUST output `auto_handle` or `escalate` with a human-readable `route_reason`.

Hard-escalate rules (non-overridable, checked before any model judgement):

| Trigger | Rationale |
|---|---|
| Account compromise / unauthorised access | Security, needs identity verification |
| Refund, chargeback, billing dispute | Financial commitment |
| Legal, regulatory, press, or data-privacy mention | Liability |
| Distress or self-harm language | Human duty of care |
| Third+ contact from same user | Prior attempts failed |
| Retrieval returns no evidence above similarity threshold | No grounding → no confident draft |
| Classifier confidence below threshold, or intent = `other` | Unknown request |

Everything else routes by model judgement.

### FR-4 — Output contract
```json
{
  "tweet_id": "string",
  "intent": "playback_error",
  "intent_confidence": 0.82,
  "draft_reply": "string",
  "route": "auto_handle | escalate",
  "route_reason": "string, one sentence, human-readable",
  "evidence_ids": ["tweet_id", "..."],
  "trigger": "rule:refund | model | null",
  "latency_ms": 1240
}
```
Every field is mandatory. `evidence_ids` may be empty only when `route == escalate` with `trigger == rule:no_evidence`.

### FR-5 — Baselines
The harness MUST evaluate, under identical conditions:
- **B0 trivial** — majority intent, one fixed canned reply, always-auto (and always-escalate reported separately).
- **B1 simple** — TF-IDF + logistic regression; kNN reply copied verbatim; keyword routing.
- **B2 LLM-only** — zero-shot, no retrieval. Isolates retrieval's contribution.
- **Full agent**.

### FR-6 — Evaluation harness
MUST produce, in one command, from cached predictions, with no API calls: intent accuracy + macro-F1 + per-class F1 + confusion matrix; escalation precision/recall/F1; retrieval hit-rate; judge scores per rubric dimension; bootstrap 95% CIs on every headline number.

### FR-7 — Judge validation
The LLM judge MUST be validated against human scores on ≥60 replies before its output is reported. MUST report quadratic-weighted Cohen's κ per dimension and judge self-consistency across two runs. Any dimension with κ < 0.4 MUST be marked unreliable and excluded from headline claims.

## 5. Data requirements

- Source: `thoughtvector/customer-support-on-twitter` (`twcs.csv`).
- Schema: `tweet_id, author_id, inbound, created_at, text, response_tweet_id, in_response_to_tweet_id`.
- Threads reconstructed via `in_response_to_tweet_id → tweet_id`; brand replies may span multiple tweets and MUST be concatenated in order.
- Retrieval corpus = (first customer tweet, first substantive brand reply) pairs, deflection-only replies filtered out.
- Preprocessing: strip `@handles`, normalise URLs to `<url>`, drop non-English, dedupe near-identical text.
- A seeded subsample (~8–10k pairs) is committed to the repo. Full dataset is never required to reproduce results.
- The pipeline MUST print a drop-report: rows removed at each stage, with reasons.

**Golden set:** 200 examples, hand-labelled, split dev (120) / test (80) **before** modelling. Test is scored exactly once, at the end. Sampling is stratified + escalation-seeded + an unbiased random slice; weights recorded so live-traffic estimates can be reweighted.

## 6. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | `make eval` reproduces every headline number in **under 15 minutes** on a laptop, from cache, offline. |
| NFR-2 | All randomness seeded; two runs of the harness give identical numbers. |
| NFR-3 | API keys via env var only; no secrets committed. |
| NFR-4 | Per-message cost and p50/p95 latency reported for the full agent. |
| NFR-5 | Every borrowed snippet, prompt pattern, or library idea cited in `DECISIONS.md`. |
| NFR-6 | No customer PII beyond what the public dataset already contains; handles stripped in all outputs. |

## 7. Success criteria (pre-registered)

**Primary — the system must beat both baselines on the test split, with non-overlapping confidence intervals where claimed.**

| Metric | Target | Why this bar |
|---|---|---|
| Intent macro-F1 | ≥ 0.65, and > B1 | 8 noisy classes; macro not accuracy, so rare intents can't be ignored |
| Escalation **recall** | ≥ 0.85 | Primary safety metric; a missed escalation is the expensive error |
| Escalation precision | ≥ 0.50, reported honestly | Over-escalation is cheap; not optimised for |
| Reply groundedness (judge) | ≥ 4.0/5, and > B1 | Core value of retrieval |
| Hallucinated URL/price rate | < 2% | Hard safety line |
| Judge κ (reported dimensions) | ≥ 0.4 | Below this the metric isn't evidence |

**Secondary:** intra-annotator agreement reported as the ceiling on any achievable score. Retrieval hit-rate reported as a diagnostic.

**Explicit non-goal:** beating the trivial "DM us" baseline on judge score by a large margin. That baseline is what the brand genuinely does, so the honest comparison is narrow and will be presented as such.

## 8. Known risks

| Risk | Impact | Mitigation |
|---|---|---|
| Brand replies are mostly deflection | No grounding possible; project collapses | Day-0 deflection gate across 4 brands before committing |
| Escalation positives too few for a stable recall estimate | Headline safety number is noise | Oversample escalation candidates; report CI width, not a point estimate |
| Judge shares model family with generator → self-preference | Inflated quality scores | Validate against human scores; consider a different judge model; flag in the misleading-number section |
| Taxonomy and labels both authored by one person | Model graded against its author's definitions — partly circular | Report intra-annotator agreement as the honest ceiling; state the circularity |
| Multi-intent tweets forced into one label | Silent accuracy loss | Measure the rate during labelling; if >15%, reconsider multi-label |
| Dataset is from 2017 | Grounded replies may cite stale policy | Named as an unmeasured production risk in the report |

## 9. Acceptance checklist

- [ ] `make data` rebuilds the subsample from source with a drop-report.
- [ ] `make agent` runs end-to-end on the golden set given an API key.
- [ ] `make eval` reproduces the README results table offline in <15 min.
- [ ] `golden_v1.jsonl` (200 labelled, dev/test flagged) + labelling guide + sampling notes committed.
- [ ] Agreement numbers reported: intra-annotator, and judge-vs-human κ per dimension.
- [ ] Results table covers B0, B1, B2, full agent, with bootstrap CIs.
- [ ] Test split scored exactly once, after dev-split iteration froze.
- [ ] Top 5 failure modes, each with a real example and a hypothesis.
- [ ] "What is misleading about my headline number?" section present.
- [ ] `DECISIONS.md` has 10–15 entries with rationale.
- [ ] Every borrowed component cited.
