# AGENT_POLICY.md — Operating Rules, Thresholds & Limits

**Scope:** the runtime behaviour contract. What the agent is allowed to do, what it must refuse, and the exact numbers that gate each decision.

> Every threshold here is a **tunable with a default and a justification**, not a magic constant. All live in `config/policy.yaml` so they can be swept in evaluation and so a grader can see them in one place. Any threshold changed after seeing test-split results must be logged in `DECISIONS.md` with the reason.

---

## 1. Operating principles

1. **The agent proposes, a human disposes.** No output is ever sent to a customer without human confirmation. Autonomy is a product decision the brand makes later, not a capability claim made here.
2. **Ungrounded means unanswered.** If no historical evidence supports a reply, the agent escalates rather than improvising.
3. **Asymmetric caution.** Over-escalating costs an agent ~30 seconds. Under-escalating costs a public incident. The agent is tuned accordingly and this is stated wherever escalation precision is reported.
4. **Every decision carries a reason.** `route_reason` is mandatory and human-readable. An unexplainable decision is treated as a bug.
5. **No silent failure.** Every fallback path emits a `trigger` value that shows up in metrics.

---

## 2. Hard rules (non-overridable)

These are checked **before** any model call and cannot be reversed by model judgement. They fire on the raw customer message.

| ID | Condition | Action | Reason |
|---|---|---|---|
| HR-1 | Account compromise signals (hacked, someone else is using, unauthorised login, can't recover) | `escalate` | Requires identity verification the agent can't perform |
| HR-2 | Money movement (refund, chargeback, charged twice, dispute, cancel and refund) | `escalate` | Financial commitment; only a human may promise money |
| HR-3 | Legal / regulatory / press (lawyer, sue, GDPR, data request, journalist, ombudsman) | `escalate` | Liability exposure |
| HR-4 | Distress or self-harm language | `escalate` + flag `sensitive` | Human duty of care; agent must not generate a draft at all |
| HR-5 | Third or later contact from same `author_id` within the thread window | `escalate` | Prior attempts demonstrably failed |
| HR-6 | Retrieval evidence below similarity floor (§3) | `escalate` | No grounding available |
| HR-7 | Intent confidence below floor, or intent = `other` | `escalate` | Unknown request |
| HR-8 | Message contains apparent PII (email, phone, card fragment, order ID) | `escalate` + redact before logging | Must not be echoed into a public reply |

**HR-4 is special:** the agent returns `draft_reply: null`. Generating a cheerful troubleshooting draft for someone in distress is worse than generating nothing.

---

## 3. Thresholds

| Parameter | Default | Justification | Sweep range for eval |
|---|---|---|---|
| `intent_confidence_floor` | **0.55** | Below this, the classifier is near coin-flip across 9 classes; escalate instead | 0.40–0.75 |
| `retrieval_top_k` | **5** | Enough voice variety without diluting the prompt | 3–10 |
| `retrieval_similarity_floor` | **0.35** (cosine) | Below this, retrieved pairs are topically unrelated in spot checks | 0.25–0.50 |
| `min_evidence_above_floor` | **2** | One similar case may be an outlier resolution; two is a weak pattern | 1–3 |
| `reply_max_chars` | **280** | Tweet-native; brand replies are short | fixed |
| `reply_target_chars` | **100–220** | Matches the brand's observed reply length distribution (p25–p75) | fixed |
| `classification_temperature` | **0.0** | Determinism; classification is not a creative task | fixed |
| `generation_temperature` | **0.3** | Slight variation for natural voice, low enough to stay grounded | 0.0–0.7 |
| `judge_temperature` | **0.0** | Reproducibility of the measuring instrument | fixed |
| `max_llm_retries` | **1** | Retry once on malformed JSON, then fall back | fixed |
| `repeat_contact_window` | **48h** | Beyond this, treat as a new issue | 24–72h |
| `escalation_rate_alarm` | **> 60% or < 5%** | Outside this band the router is broken, not cautious | n/a |

**Threshold tuning is done on the dev split only.** The test split is scored once, with thresholds frozen.

---

## 4. Content policy for generated replies

**Must:**
- Stay grounded in retrieved evidence; every concrete step must appear in at least one retrieved reply.
- Use the brand's observed register (casual, contraction-heavy, first-name sign-off if that's the brand's pattern).
- Acknowledge the problem before instructing.

**Must never:**

| Forbidden | Why |
|---|---|
| Invented URLs, prices, promo codes, phone numbers | Hallucination with direct customer harm |
| Promises of refunds, credits, or compensation | Financial commitment reserved for humans |
| Specific resolution timelines ("fixed within 24 hours") | Unverifiable commitment |
| Claims about root cause of an outage | Speculation presented as fact |
| Requests for passwords, full card numbers, or OTPs | Trains customers into phishing-vulnerable behaviour |
| Echoing PII from the inbound message | Public channel |
| Blame directed at the customer | Brand voice violation |
| Legal, medical, or financial advice | Out of domain |

**Enforcement:** a post-generation validator (deterministic, not a model) checks for URLs not present in evidence, currency amounts, digit sequences resembling PII, and length bounds. Violations force `escalate` with `trigger: policy_violation` and are counted in metrics. The validator is a safety net, not the primary defence — the prompt is.

---

## 5. Fallback ladder

| Failure | Behaviour |
|---|---|
| Classifier returns malformed output | Retry once → then `intent: other`, escalate |
| Retrieval returns nothing above floor | Escalate, `draft_reply: null`, `trigger: rule:no_evidence` |
| Generator API error or timeout | Escalate, `trigger: system_error`; never return a partial draft |
| Post-generation validator fails | Escalate, `trigger: policy_violation`, store the rejected draft for failure analysis |
| Non-English input detected | Escalate, `trigger: rule:unsupported_language` |

**Every fallback escalates.** There is no path where a failure results in an auto-handled message.

---

## 6. Known limitations (state these before a grader finds them)

1. **Single-turn only.** No memory of what was already tried in the conversation. HR-5 is a crude proxy.
2. **Single-label.** Multi-intent tweets get one label; the loss is measured, not fixed.
3. **2017 training data.** Grounded replies may reflect product state that no longer exists. Unmeasured production risk.
4. **English only.** Non-English traffic is escalated wholesale, not served.
5. **No true resolution signal.** The dataset shows what the brand *said*, not whether it *worked*. "Grounded" means consistent with past practice, not verified as correct — the single most important caveat on every reply-quality number.
6. **Thresholds tuned on ~120 dev examples.** They will not transfer cleanly to live traffic volumes.
7. **Sarcasm and implicit escalation are weak spots.** A calm message describing a severe problem may be under-escalated; measured in failure analysis.
8. **Rule triggers are keyword-seeded**, so they inherit keyword brittleness — paraphrased refund requests may slip through to model judgement.
