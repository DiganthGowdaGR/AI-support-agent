# PLAN.md — Hiver SDE Intern Take-Home

**Deliverable:** an AI support agent for one brand (classify → draft reply → route) plus the evidence that it can be trusted.

**Core bet:** the graders said the proof is worth more than the system. So the time split is roughly **30% agent, 70% evaluation + analysis + writing**. A mediocre agent with a rigorous, self-critical eval beats a clever agent with a vague "it works well."

---

## 0. Brand choice

**Recommendation: `SpotifyCares`.** Rationale:

- ~43k tweets — big enough for retrieval, small enough to work with locally.
- Product-domain intents are crisp and separable (playback, billing, account access, family plan, content availability, device integration). Airlines collapse into "my flight is broken" with dozens of unlabelable edge cases.
- Replies often contain **actual troubleshooting steps**, not pure deflection.

That last point is the whole ballgame and must be verified, not assumed. Many brands in this dataset (AmazonHelp, AppleSupport) reply to nearly everything with "DM us and we'll take a look." If the historical replies carry no substance, there is nothing to ground a draft reply in and the whole assignment degenerates.

**Day 0 gate — the deflection check.** Before committing, sample 100 brand replies from each of `SpotifyCares`, `AppleSupport`, `Uber_Support`, `TMobileHelp`. Hand-classify each as *substantive* (contains a concrete step/answer) vs *deflection* (DM request, apology only, link to a form). Pick the brand with the highest substantive rate. Record the number — it belongs in the decision log and it pre-empts an obvious interview question ("why this brand?").

Fallback if Spotify's substantive rate is low: `TMobileHelp` or `Ask_Spectrum` (telco troubleshooting tends to be step-heavy).

---

## 1. Scope — what I am building and what I am explicitly not

**Building:** a single-turn function. Input = one inbound customer tweet (plus minimal thread context if it exists). Output = `{intent, confidence, draft_reply, route, route_reason, evidence_ids}`.

**Not building (state this in the report, it's graded):**
- Multi-turn dialogue state / conversation management.
- Live Twitter integration, UI, deployment, auth.
- Fine-tuning. Retrieval + prompting only, given time budget.
- Intent taxonomy beyond ~8 classes. Long tails get an `other` bucket and honest reporting of how big it is.
- Banking77. Different domain (banking vs music streaming), so transferring its labels would inject a taxonomy that doesn't fit this brand's data. May use it only as a sanity check that the classifier code works on a known-labelled set — and will say so rather than pretending it's a contribution.

**What "good" means for this brand** (write this before building anything, so metrics follow the definition rather than the other way round):
1. Never send a confidently wrong instruction to a paying customer.
2. Never auto-handle an angry, compromised-account, or refund case.
3. Match the brand's actual voice — Spotify's agents are casual, first-name signed, emoji-light.
4. Being slightly over-cautious on escalation is cheap; missing an escalation is expensive. **Escalation recall is the primary safety metric.**

---

## 2. Phases

### Phase 1 — Data pipeline (½ day)

`twcs.csv` schema: `tweet_id, author_id, inbound, created_at, text, response_tweet_id, in_response_to_tweet_id`. Customers have numeric `author_id`; brands have handle strings. `inbound=True` = customer → brand.

Tasks:
- Filter to threads involving the chosen brand.
- **Reconstruct threads** by joining `in_response_to_tweet_id` → `tweet_id`. Handle the messy parts: a brand reply split across multiple tweets, customers replying to themselves, orphan tweets whose parent isn't in the dump.
- Build the core artifact: **(first customer tweet, first substantive brand reply)** pairs. This is both the retrieval corpus and the source of golden examples.
- Clean: strip `@handles`, URLs → `<url>`, collapse whitespace, drop non-English (langdetect), dedupe near-identical tweets.
- **Freeze a subsample** (~8–10k pairs) with a fixed seed and commit it. The graders won't run the full 3M.

Acceptance: `python src/build_dataset.py` produces `data/threads.parquet` + a printed report of how many tweets were dropped at each step and why. Drop-rate transparency is cheap credibility.

### Phase 2 — Intent taxonomy (½ day)

Discovery is manual-first, clustering-assisted:
1. Read 200 random customer tweets by hand. Write down recurring themes. This is non-negotiable — taxonomies invented from cluster labels alone are usually unlabelable in practice.
2. Embed the corpus, run KMeans/HDBSCAN at a few `k`, inspect top terms and 10 samples per cluster. Use this only to check whether the hand-derived list missed a real cluster or merged two distinct ones.
3. Finalise ~8 intents. Starting hypothesis for Spotify:
   `playback_error`, `account_access`, `billing_subscription`, `plan_management` (family/student/duo), `content_availability`, `device_integration`, `feature_feedback`, `praise_offtopic`, `other`.
4. Write a **one-paragraph definition + 2 positive + 2 boundary examples per intent** in `golden/labelling_guide.md`. The boundary examples matter most: "billing_subscription vs plan_management — a failed charge is billing; wanting to remove a family member is plan_management."

### Phase 3 — Golden set (1½ days, the centerpiece)

**Sampling (200 examples):**
- 120 stratified random across predicted-intent clusters, so rare intents aren't invisible.
- 40 oversampled likely-escalation cases (keyword seeds: refund, hacked, charged twice, cancel, lawyer, unacceptable, still not working). Escalations are rare; a pure random sample gives too few positives to measure recall on.
- 40 pure random, untouched, as an unbiased slice for estimating real-world distribution.
- **Record the sampling weights.** Metrics on a stratified set are not metrics on live traffic, and the report must say so.

**Labelling per example:** `intent`, `route` (auto/escalate), `route_reason`, `difficulty` (easy/hard), `notes`. Use the frozen guide; when an example forces a guide change, amend the guide and **re-label everything already done**.

**Rigor moves that cost little and score a lot:**
- **Split the golden set into dev (120) and test (80) up front.** Only look at dev while iterating. Run test once, at the end. Reporting a number you didn't tune against is the single most persuasive thing in the whole submission.
- **Intra-annotator agreement:** re-label 40 examples 24h later without looking at the first pass. Report agreement. If I disagree with myself 15% of the time, no model can be scored above that ceiling — and stating that ceiling explicitly is exactly the self-awareness the brief is fishing for.
- If a second person is available for even 30 examples, get inter-annotator agreement too.

Acceptance: `golden/golden_v1.jsonl` + `golden/labelling_guide.md` + `golden/sampling_notes.md` with agreement numbers.

### Phase 4 — Baselines (½ day)

Build these **before** the LLM agent so the bar is set honestly.

- **B0 trivial:** majority intent for everything; one fixed canned reply ("Hey! Sorry about that — shoot us a DM and we'll dig in 🎧"); report both always-auto and always-escalate routing.
- **B1 simple:** TF-IDF + LogisticRegression for intent; kNN retrieval that **copies the nearest historical brand reply verbatim**; keyword rules for routing.
- **B2 LLM-only:** zero-shot LLM classification + reply generation, no retrieval. Isolates how much retrieval actually contributes.

Expect B0's canned reply to score respectably on the judge rubric, because it's what the brand genuinely does. That is a finding, not an embarrassment — it goes straight into the "misleading headline number" section.

### Phase 5 — The agent (1 day)

```
classify → retrieve → generate → route
```

- **Classify:** LLM with the taxonomy definitions + k few-shot examples drawn only from the dev split. Return a confidence or a structured refusal (`other`).
- **Retrieve:** embed the incoming tweet, pull top-k similar historical *(customer, brand reply)* pairs, filtered to substantive replies. Return their IDs as `evidence_ids`.
- **Generate:** prompt with the retrieved pairs as in-context grounding + a short brand-voice spec. Forbid inventing links, prices, dates, or policy.
- **Route:** hybrid. Hard rules fire first and are non-overridable (account compromise, refund/chargeback, legal threat, self-harm/distress language, third contact from the same user). LLM judgement handles the rest. `route_reason` is always a human-readable sentence — required by the brief and needed for failure analysis.

### Phase 6 — Evaluation harness + judge validation (1 day)

**Automated:**
- Intent: accuracy, **macro-F1** (headline — accuracy flatters a dominant class), per-class F1, confusion matrix.
- Routing: precision/recall/F1 on the `escalate` class specifically. Report the confusion matrix, not a single number.
- Retrieval: hit-rate — does at least one retrieved example share the gold intent.
- Cheap reply proxies: hallucinated-URL rate, length distribution vs the brand's real replies.

**LLM-as-judge:** 1–5 rubric, one dimension at a time, scored blind to which system produced the reply, with position shuffling:
`groundedness` (supported by retrieved evidence), `relevance`, `actionability`, `tone_match`, `safety` (does it promise something it shouldn't).

**Judge validation — do not skip:**
- I personally score 60 replies on the same rubric, blind, before seeing judge output.
- Report **Cohen's κ (quadratic-weighted)** and Spearman correlation per dimension.
- Report judge self-consistency: run it twice at temperature 0 and again at 0.7.
- If κ < 0.4 on a dimension, **the judge is not usable for that dimension** — say so and fall back to human-only scoring on a smaller sample. A validated judge on 60 examples beats an unvalidated judge on 200.

### Phase 7 — Failure analysis (½ day)

Read **every** error on the dev split. Not a sample. Group into 5 modes, each with: real example, gold vs predicted, hypothesis for the cause, proposed fix, and whether the fix is cheap.

Likely candidates to look for:
- Sarcasm read as praise ("great, another outage, love it").
- Multi-intent tweets (billing + playback in one message) forced into one label.
- `other` absorbing everything ambiguous, inflating apparent accuracy elsewhere.
- Retrieval pulling topically similar but *differently resolved* cases → confidently wrong steps.
- Escalation triggered by profanity rather than by actual severity.
- Replies grounded in 2017 policy that is now stale (the dataset is old — a real production risk worth naming).

### Phase 8 — Report, decision log, reproducibility (1 day)

**"What is misleading about my headline number?"** — pre-register the candidates now, verify later:
- The golden set is stratified, so metrics ≠ live-traffic performance. Give the reweighted estimate too.
- n=200 means a 95% CI of roughly ±7pp. Bootstrap it and show the interval rather than a bare point estimate.
- I wrote both the taxonomy and the labels, so the model is being graded against my own definitions — partly circular. Intra-annotator agreement is the honest ceiling.
- The judge shares a model family with the generator → plausible self-preference bias.
- The trivial "DM us" baseline is a real production strategy, so beating it on rubric score is a weaker claim than it sounds.
- Escalation recall rests on ~40 positives; the CI is wide.
- Data is from 2017; distribution shift against today's product is unmeasured.

**15-minute reproducibility:** commit the data subsample and **cached model outputs**. `make eval` must regenerate the headline table from cache with zero API calls. A separate `make agent` re-runs generation for anyone who supplies a key. State runtime and cost for both paths in the README.

---

## 3. Repo layout

```
README.md              # headline results + 15-min repro instructions
report.md              # max 6 pages
DECISIONS.md           # 10-15 non-obvious calls
Makefile               # make data | make agent | make eval
data/
  twcs_sample.parquet  # frozen subsample, seeded
  threads.parquet
golden/
  golden_v1.jsonl      # 200 labelled, dev/test flagged
  labelling_guide.md
  sampling_notes.md
  agreement.md
src/
  build_dataset.py  taxonomy.py  classify.py
  retrieve.py  generate.py  route.py  baselines.py  agent.py
eval/
  run_eval.py  judge.py  judge_validation.py  metrics.py
outputs/
  cached_predictions/  figures/
notebooks/
  01_explore.ipynb  02_clustering.ipynb
```

---

## 4. Schedule (6 days; compression notes below)

| Day | Focus | Done when |
|---|---|---|
| 0 | Brand gate, repo scaffold, data load | Deflection rates measured, brand locked |
| 1 | Pipeline + taxonomy | `threads.parquet` + labelling guide frozen |
| 2 | Golden set pass 1 (all 200) | `golden_v1.jsonl` complete |
| 3 | Re-label 40 for agreement; baselines B0/B1/B2 | Baseline table exists |
| 4 | Agent build + eval harness | End-to-end run on dev split |
| 5 | Judge + judge validation + failure analysis | κ reported, 5 modes written |
| 6 | Test-split run (once), report, decision log, README | Submission ready |

**If only 3 days:** cut the golden set to 150, drop B2, drop clustering (hand-derive the taxonomy), validate the judge on 40 instead of 60. **Never cut:** the golden set, judge validation, failure analysis, the misleading-number section. Those are the graded parts.

---

## 5. Decision log seeds

Capture these as they happen rather than reconstructing them at the end:

1. Brand choice and the deflection-rate evidence behind it.
2. Single-turn framing over multi-turn, and what it costs.
3. Eight intents rather than twenty — the long-tail tradeoff.
4. Keeping an explicit `other` class instead of forcing a label.
5. Stratified + keyword-seeded sampling, and why pure random would have under-sampled escalations.
6. Dev/test split of the golden set, decided before any modelling.
7. Hard rules that override LLM routing, and which ones.
8. Optimising escalation recall over precision (asymmetric cost).
9. Macro-F1 as headline rather than accuracy.
10. Retrieval over fine-tuning.
11. Grounding judged against retrieved evidence, since true resolution outcomes are unobservable in this dataset.
12. Rejecting Banking77 for taxonomy transfer.
13. Judge rubric scored per-dimension rather than as one overall score.
14. Caching predictions for reproducibility, and what that hides.
15. Dropping non-English tweets, and the coverage that loses.

---

## 6. Open questions to resolve early

- How many brand replies are substantive vs deflection? (gates everything)
- What fraction of inbound tweets have a reply at all? (retrieval corpus size)
- Does thread reconstruction work, or are parents missing too often?
- How many tweets are genuinely multi-intent? (if >15%, consider multi-label)
- What's the realistic escalation base rate in the unbiased 40?
