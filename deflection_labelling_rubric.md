# Deflection Gate — Labelling Rubric

Use this while filling `hand_label` in `outputs/gate/gate_sample.csv`.
Hide the `heuristic` column first. Seeing it will anchor you and destroy the whole
point of the comparison.

---

## The test question

> **Could a support agent send this reply as-is and have a reasonable chance of
> resolving the customer's issue without further back-and-forth?**

Not "does it contain a verb." Not "is it polite." Resolution potential is the only
thing that matters, because that is what a draft reply has to do.

---

## Labels

**`substantive`** — contains a specific action, answer, or explanation the customer
can act on now.
- "Try logging out and back in from Settings > Account, that usually clears it."
- "That podcast was pulled by the publisher in your region, so it won't show up."
- "This is a known issue with 8.5.2 — updating to 8.5.3 fixes it."

**`deflection`** — routes the customer elsewhere instead of helping here.
- "Sorry about that! DM us your details and we'll take a look."
- "Please fill out the form at <url>."
- "We're sorry for the trouble. Our team will be in touch."

**`unclear`** — genuinely ambiguous. Use sparingly; if you're over ~15% unclear,
you're avoiding decisions.
- Pure acknowledgement with no action either way: "Thanks for flagging this!"
- Reply is unintelligible without the missing thread context.

---

## Boundary rules (decide these once, apply consistently)

| Case | Label | Why |
|---|---|---|
| A real step **and** a DM ask — "update the app, then DM us if it persists" | **substantive** | The step alone might resolve it; the DM is a fallback |
| A DM ask with a token gesture — "have you tried restarting? DM us" | **deflection** | The "step" is filler; the actual ask is the channel switch |
| Links to a help article with no inline step | **deflection** | The answer lives somewhere else, so there's nothing to ground on |
| Links to an article **and** summarises the fix inline | **substantive** | The inline summary is groundable |
| Explains *why* something happens but gives no fix | **substantive** | An explanation is a resolution for "is this broken?" questions |
| Apology + timeline promise, no action | **deflection** | Nothing for a customer to do |
| Asks a diagnostic question — "which device are you on?" | **deflection** | Legitimate support, but it defers rather than resolves |

That last one is a judgment call and reasonable people differ. Whichever way you go,
go the same way every time, and record the choice in `DECISIONS.md`.

---

## Process

1. Sort by `brand`. Label one brand at a time — switching contexts costs consistency.
2. Label **at least 40 per brand**. Below that, the per-brand rate has a confidence
   interval wide enough to make the ranking meaningless.
3. Label blind to the `heuristic` column.
4. **Keep a running notes file while you label.** You are reading real customer
   messages for the first time, and the intent taxonomy will start forming itself.
   Jot every recurring theme — that work is Phase 2, done early and for free.
5. If you change a boundary rule mid-pass, go back and re-label everything already
   done under the old rule. A rubric that drifts mid-labelling produces a golden set
   nobody should trust, including you.

## Expected output

- `hand_label` filled for ≥240 rows
- `notes/intent_themes.md` — running list of recurring customer problems
- Two or three `DECISIONS.md` entries: the resolution-potential definition, the
  diagnostic-question call, and anything the heuristic got badly wrong
