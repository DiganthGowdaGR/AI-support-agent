# DECISIONS.md

Non-obvious decisions, threshold changes, and cited sources. Appended as made, not
reconstructed after the fact.

1. **Six candidate brands for the deflection gate:** SpotifyCares, TMobileHelp,
   Ask_Spectrum, AppleSupport, AmazonHelp, Uber_Support. Chosen for volume plus
   plausibly step-heavy support domains. AppleSupport and AmazonHelp were
   deliberately pre-registered as expected-low negative controls, so the gate
   would have a real disconfirming case rather than only confirming a brand
   already preferred.

2. **AppleSupport scored #1 on heuristic substantive% (27.1%), falsifying the
   pre-registered expectation that it would be a negative control.** Treated as
   the gate working as intended, not a bug — the whole point of registering a
   prior before running the heuristic was to have something that could be
   wrong. Not corrected for or re-weighted; hand-labelling will confirm or
   overturn it before any brand is picked.

3. **Heuristic substantive rates top out at 27% (AppleSupport) and the median
   candidate is well below that.** The groundable corpus — replies that
   actually carry a retrievable step — is roughly 4x smaller than raw
   outbound-reply counts suggest. Raw reply volume is not being used as a
   proxy for retrieval-corpus size in brand selection.

4. **`reply_rate` (outbound replies / inbound @mentions) is unreliable and
   excluded from brand selection.** TMobileHelp (1.561) and SpotifyCares
   (1.379) both exceed 1.0, which is only possible if the `@brand`-mention
   text search undercounts true inbound volume (e.g. replies in threads
   without an explicit @-mention). The metric is kept in `gate_summary.csv`
   for visibility but is not treated as a demand signal.

5. **High unclear% for AmazonHelp (65.8%) and SpotifyCares (48.7%) is treated
   as a probable heuristic gap, not genuine reply ambiguity.** `SUBSTANTIVE_RE`
   is a fixed keyword list; short, brand-specific substantive replies (e.g.
   order-status or account-lookup phrasing that isn't "try/restart/settings"
   shaped) plausibly fall through both pattern lists. These two brands are
   probably undercounted on substantive% relative to their hand-labelled
   truth, and their heuristic numbers should be weighted less heavily than
   brands with low unclear%.

6. **Override of the "never write eval labels" rule for `outputs/gate/gate_sample.csv`
   only (CLAUDE.md working rules), authorized explicitly by the human on
   2026-09-14.** All 594 rows of `gate_sample_labelled.csv` were labelled by
   Claude (blind to the `heuristic` column, one rubric pass per brand,
   `deflection_labelling_rubric.md` applied including the diagnostic-question
   boundary rule), not hand-labelled by a human. This is explicitly **not**
   the phase-4 golden set, and that rule is unchanged and still stands.
   Consequence: the heuristic-vs-label agreement numbers below are
   model-vs-regex, not model-vs-independent-human-judgment — they cannot
   serve as the calibration check the gate script's docstring originally
   intended. Brand selection made from this round of labelling rests on
   LLM-generated labels with human spot-check only (13 rows self-flagged
   `confidence: low`), not on independent hand labels.

   Overall heuristic agreement: **40.2%** (well below the script's own 70%
   reliability bar). Per brand: SpotifyCares 57.6%, AppleSupport 42.4%,
   TMobileHelp 42.4%, Uber_Support 40.4%, Ask_Spectrum 35.4%, AmazonHelp
   23.2%. Substantive rate per brand (LLM labels, n=99 each): SpotifyCares
   27.3%, AmazonHelp 22.2%, TMobileHelp 14.1%, Uber_Support 13.1%,
   AppleSupport 11.1%, Ask_Spectrum 5.1% — a materially different ranking
   from the heuristic's (AppleSupport 27.1% highest, see decision #2), driven
   largely by the regex's inability to distinguish an instruction ("try
   restarting") from a diagnostic question ("have you tried restarting?"),
   which the rubric treats as deflection.

7. **Correction to decision #6: the 20-row spot check was inter-model
   agreement, not a human audit.** The "my_label" column in
   `outputs/gate/spot_check.csv` was filled by a different LLM, not a human.
   Decision #6's phrase "human spot-check" is wrong and superseded by this
   entry — **no row in this entire Day-0 gate (594-row pass or 20-row spot
   check) has been labelled by a human.** Provenance note: the reported
   spot-check counts below were given to Claude directly by the human: as of
   this entry, `outputs/gate/spot_check.csv` on disk still shows every
   `my_label` cell blank (checked immediately before writing this entry, possibly
   a OneDrive sync lag or a review done in a copy Claude doesn't have access
   to), so the per-row agreement/disagreement breakdown could not be
   independently verified from the file — only the summary counts below are
   recorded.

   **Second-reviewer (LLM) split:** AppleSupport 2/10 substantive,
   SpotifyCares 2/10 substantive. At n=10 per brand this is not a
   statistically meaningful separation — the confidence interval on a
   substantive-rate estimate from 10 samples is roughly ±25 points, wider
   than the entire gap between any two candidate brands. **This sample
   cannot decide the brand and never could have; it was underpowered by
   design (n=20 total was a spot-check, not a comparison).**

   **What the spot check does support:** both AppleSupport and SpotifyCares
   deflect roughly 80% of the time under independent (LLM) review — broadly
   consistent with the 594-row pass's ranking of both brands as more
   deflection-heavy than average. It also corroborates decision #2/#6's
   explanation for the heuristic's original AppleSupport-on-top result: that
   ranking was an artifact of the regex matching step-verbs (`restart`,
   `check`, `try`) embedded inside diagnostic questions, not genuine
   substantive content — the second reviewer's 2/10 for Apple lines up with
   the 594-row pass's 11.1% far better than with the heuristic's 27.1%.

8. **Brand decision: SpotifyCares.** Chosen on two grounds: (1) the 594-row
   LLM-labelled pass (decision #6), where SpotifyCares had the highest
   substantive rate (27.3%) of all six candidates; and (2) transferability of
   the substantive content — Spotify's groundable fixes are largely
   product-level (feature availability, reinstall steps, subscription/billing
   status) and generalise across customers, whereas AppleSupport's are mostly
   device- and iOS-version-specific and AmazonHelp's are mostly
   order-specific, both of which ground less well in a shared retrieval
   corpus. This decision rests entirely on LLM-generated labels (both the
   594-row pass and the 20-row spot check) — no human has hand-labelled any
   row at any stage of the Day-0 gate. That caveat carries forward into every
   later phase that treats this brand choice as settled.

9. **MinHash near-dup removal (Phase 1, `src/build_dataset.py`) runs on
   `customer_text_clean` only, deliberately — it does not deduplicate brand
   replies.** This was flagged as a gap during a Phase-1 corpus audit (should
   have been logged when the pipeline was first built, not after). It's the
   right scope for its stated purpose: ARCHITECTURE.md's own justification
   for the step is "so the golden set isn't 15 copies of the same
   *complaint*" — complaint means the customer message, since that's what
   later gets sampled into the golden set. Confirmed working on that target:
   zero exact-duplicate `customer_text_clean` values remain in the 37,853-row
   corpus, and 331 near-dupes were removed. It was never meant to, and does
   not, address brand-reply template repetition — e.g. the "Taylor Swift
   'Reputation' isn't available yet" reply appears (with cosmetic
   personalization) in 243 raw rows, none of which get merged by this step.
   That repetition is real signal, not noise: 243 different customers
   independently asked and each legitimately grounds to the brand's one true
   answer. Collapsing it at the corpus level would destroy retrieval
   evidence. See decision #10 for where the corresponding dedup belongs.

10. **Requirement for the retrieval phase (not yet built): retrieval must
    deduplicate its returned evidence set on normalised reply text, and
    `min_evidence_above_floor` (config/policy.yaml) must count distinct
    replies, not rows.** Because brand-reply templates are kept undeduplicated
    in the corpus by design (decision #9), a naive top-k retrieval could
    return five rows that are all the same canned "Reputation isn't
    available" reply. `min_evidence_above_floor: 2` exists to guard against
    grounding a draft in a single outlier resolution — five copies of one
    reply must not satisfy that guard, since it's still exactly one
    independent case. The retrieval module must normalise (strip
    handles/URLs/signatures, as done for the Phase-1 frequency audit) and
    count distinct reply texts above the similarity floor before checking
    against `min_evidence_above_floor`. Not implemented yet — corpus.parquet
    itself is untouched by this decision.

11. **Language filter fix: `lang_min_words: 6` carve-out
    (`config/policy.yaml`), plus content-free rows rerouted from
    `non_english` to `empty_after_clean`.** A diagnostic on a 30-row sample
    of `non_english` drops found 19/30 (63%) were unambiguously English,
    almost all short (langdetect is known-unreliable under ~6 words); 5/30
    were correctly non-English; 5/30 were content-free after cleaning
    (`<url>` or `__email__` only, misclassified as a language failure when
    there was no language to detect); 1/30 was a single ambiguous word. Fix:
    rows with `customer_text_clean` under `lang_min_words` are kept and
    tagged `lang_uncertain` instead of being dropped; langdetect still
    applies as before at or above that length. Content-free rows are now
    caught before language detection ever runs and counted as
    `empty_after_clean`, so the drop report's reason codes describe the
    actual failure, not a downstream symptom of it.
