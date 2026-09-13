# TESTING.md — Test Strategy

Two kinds of testing, easy to conflate and important not to:

- **Correctness testing** — does the code do what it says? Deterministic, fast, binary pass/fail, runs in CI.
- **Quality evaluation** — is the agent's *judgement* good? Statistical, noisy, reported with confidence intervals, never a pass/fail gate.

Most take-homes ship one or the other. Shipping both, and being explicit about which claims rest on which, is part of the argument for trustworthiness.

---

## 1. Test pyramid

```
        ┌───────────────────────────┐
        │  Quality eval (n=200)     │  statistical, reported, not gating
        ├───────────────────────────┤
        │  Regression tests (n=25)  │  frozen cases, gating on behaviour change
        ├───────────────────────────┤
        │  Integration (n~15)       │  stage wiring, contracts, fallbacks
        ├───────────────────────────┤
        │  Unit (n~60)              │  deterministic logic, fast, exhaustive
        └───────────────────────────┘
```

---

## 2. Unit tests — deterministic logic only

Target: everything that doesn't call a model. These should be near-exhaustive, because they're cheap and they cover the safety-critical surface.

**`test_guard.py`** — the highest-value suite in the repo, since guard rules are the safety floor.
- Each hard rule HR-1..HR-8: a positive case, a paraphrase, a near-miss negative.
- Negative controls that must *not* fire: "refund" inside an unrelated word, "sue" as a name, quoted text.
- PII redaction: email, phone, card fragment, order ID — redacted in logs, and the original never reaches the generator.
- Rule precedence when two rules fire (lowest ID wins; assert it).

**`test_validate.py`** — the other safety backstop.
- URL in draft but not in evidence → violation; URL present in evidence → pass.
- Currency amounts, digit runs, promise phrases ("we'll refund", "within 24 hours").
- Length bounds at 279/280/281 chars.
- Unicode, emoji, and RTL text don't crash the checker.

**`test_thread_reconstruction.py`** — where silent data corruption lives.
- Multi-tweet brand reply concatenates in timestamp order.
- Missing parent → row dropped and counted, not silently joined to the wrong tweet.
- Customer self-reply doesn't get treated as a brand reply.
- Circular reference doesn't hang.
- Drop report totals reconcile: `input_rows == kept + sum(dropped_by_reason)`. This single assertion catches most pipeline bugs.

**`test_retrieve.py`** — with a fixed toy corpus and stubbed embeddings.
- Similarity floor excludes correctly; `min_evidence` gate fires at 1 vs 2.
- Intent filter applied; empty result handled, not crashed on.
- Ranking is stable and deterministic under the seed.

**`test_metrics.py`** — testing the measuring instrument itself.
- Macro-F1 against a hand-computed 3-class example.
- Bootstrap CI width shrinks as n grows; CI contains the point estimate.
- Cohen's weighted κ against a published worked example (cited).
- Empty-class and single-class edge cases don't silently return 0 or NaN.

> A bug in `metrics.py` invalidates every number in the report. It gets tested harder than the agent.

**`test_schema.py`** — `AgentOutput` fields present and typed; `evidence_ids` empty only when escalating with `rule:no_evidence`; `route_reason` never empty.

---

## 3. Integration tests — stage wiring, with mocked LLM

Mocked model responses (fixtures in `tests/fixtures/llm_responses/`), so these are deterministic and run offline in CI.

- Guard fires → pipeline short-circuits; no LLM call is made (assert the mock was never invoked); `draft_reply is None` for HR-4.
- Low confidence → escalates before retrieval.
- Retrieval below floor → escalates, `trigger: rule:no_evidence`.
- Validator fails → escalates, rejected draft retained.
- Malformed classifier JSON → exactly one retry, then `other` + escalate.
- API timeout → `trigger: system_error`, never a partial draft.
- **No fallback path ever returns `auto_handle`.** Parametrised across every failure mode — this is the single most important integration assertion in the suite.
- Each baseline (B0/B1/B2) runs end-to-end and emits a schema-valid output.

---

## 4. Leakage tests — treated as correctness, not as diligence

These are assertions, not intentions. Discipline fails under time pressure; assertions don't.

- No golden-set `tweet_id` appears in the retrieval corpus.
- No test-split example appears in any few-shot prompt.
- Few-shot examples come only from the dev split.
- `run_eval.py --split test` aborts unless `outputs/dev_frozen.lock` exists.
- Judge prompts contain no system identifier.

## 5. Reproducibility tests

- Two runs of `build_dataset.py` produce identical file hashes.
- Two runs of `run_eval.py` from cache produce identical metrics.
- Cache key changes when the prompt changes (guards against stale results being reported for a new prompt).
- `make eval` runs offline: network disabled, must still succeed.
- Timed: `make eval` completes in under 15 minutes on a cold clone. **Asserted in CI**, because it's an explicit requirement of the brief and a promise easy to break accidentally.

## 6. Regression tests — behavioural, frozen

25 hand-picked cases in `tests/regression_cases.jsonl`, each with an expected *route* and a note on why it matters. Chosen to cover: every hard rule, each intent, the three worst failure modes found in analysis, and five known-tricky cases (sarcasm, multi-intent, calm-but-severe).

These assert **routing**, not exact reply text — asserting generated strings makes the suite fail on every harmless rewording. Route is the decision that carries risk, so route is what's frozen.

When a regression case legitimately changes, the expectation is updated **and** a line is added to `DECISIONS.md`. An expectation changed without a recorded reason is indistinguishable from a bug being papered over.

## 7. Quality evaluation — statistical, non-gating

Covered in depth by `plan.md` §6. Summarised here for the boundary it draws:

| Property | Correctness tests | Quality eval |
|---|---|---|
| Output | pass/fail | score + 95% CI |
| Runs in CI | yes | no (cost, latency) |
| Blocks a commit | yes | never |
| n | ~100 assertions | 200 golden examples |
| Reported in the report? | one line ("suite green") | the entire results section |

**Quality numbers never gate.** A CI threshold on macro-F1 creates an incentive to tune until green, which is exactly the circularity the report is supposed to expose.

## 8. Testing the judge

The judge is an instrument, so it gets instrument tests:

- **Human agreement:** 60 replies scored by me, blind, before seeing judge output → quadratic-weighted κ + Spearman per dimension.
- **Self-consistency:** same inputs twice at temp 0 (should be near-identical) and twice at temp 0.7 (spread quantifies judge noise).
- **Position bias:** identical reply presented in slot A vs slot B; systematic score differences indicate order effects.
- **Known-bad injection:** deliberately hallucinated replies (invented URL, fabricated refund promise) injected into the judged set. A judge that scores these ≥4 on groundedness or safety is **not measuring what it claims to**, and that finding outranks any score it produces.
- **Self-preference probe:** if time allows, a second judge from a different model family on the same 60; divergence is reported rather than averaged away.

## 9. CI

```yaml
on: [push, pull_request]
jobs:
  - lint            # ruff, black --check
  - unit            # pytest tests/unit, <30s, no network
  - integration     # mocked LLM, no network
  - leakage         # assertion suite
  - repro           # make eval from cache, network disabled, timed <15min
```

No job calls a live API. CI that depends on a paid endpoint is CI that's red on someone else's clone.

## 10. What is not tested, and why

| Untested | Reason | Risk carried |
|---|---|---|
| Live API behaviour | Cost, flakiness, non-determinism | Real integration breakage would surface only on `make agent` |
| Prompt quality | Not unit-testable; that's what quality eval is for | Regressions from prompt edits caught only by regression cases |
| Load / concurrency | Batch offline tool, no concurrency requirement | Irrelevant at this scope, would matter in production |
| Embedding model quality | Treated as a fixed dependency | A weak embedder silently caps retrieval quality; hit-rate is the only proxy |
| Non-English handling | Escalated wholesale; can't evaluate what I can't read | Unknown behaviour on ~5% of raw traffic |
| Adversarial / prompt-injection inputs | Out of scope for a support-triage take-home | A crafted tweet could plausibly manipulate the generator — named as a production gap, not a solved problem |
