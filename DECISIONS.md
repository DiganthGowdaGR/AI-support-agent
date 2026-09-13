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
