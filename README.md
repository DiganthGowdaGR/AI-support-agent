# AI Support Agent

Take-home assignment: an AI customer-support agent for one brand from the Kaggle
["Customer Support on Twitter"](https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter)
dataset. It classifies an inbound tweet, drafts a grounded reply, and decides
auto-handle vs escalate.

**This project is graded on the evaluation, not the agent.** A mediocre agent with
rigorous, self-critical evidence beats a clever agent with vague claims — every
tradeoff below is made accordingly.

## Design docs

The spec lives in [`docs-skills/`](docs-skills/) and is authoritative — code should
never contradict it silently:

| Doc | Governs |
|---|---|
| [`PRD.md`](docs-skills/PRD.md) | I/O contract, scope, pre-registered targets, acceptance checklist |
| [`ARCHITECTURE.md`](docs-skills/ARCHITECTURE.md) | Module boundaries, data flow, caching, tech choices |
| [`AGENT_POLICY.md`](docs-skills/AGENT_POLICY.md) | Hard rules, thresholds, forbidden content, fallback ladder |
| [`SKILLS.md`](docs-skills/SKILLS.md) | Per-capability contracts and failure modes |
| [`TESTING.md`](docs-skills/TESTING.md) | Test strategy, leakage assertions, CI |
| [`plan.md`](docs-skills/plan.md) | Phase order and schedule |

## Build order

Built one phase at a time, no scaffolding ahead:

1. **Day 0 — deflection gate, brand selection** *(current)*
2. Data pipeline + thread reconstruction + drop report
3. Intent taxonomy + labelling guide
4. Golden set (hand-labelled, not model-labelled)
5. Baselines B0/B1/B2
6. Agent stages S1–S6
7. Eval harness + judge + judge validation
8. Failure analysis, report, decision log

## Status

Day 0 in progress: [`00_deflection_gate.py`](00_deflection_gate.py) has run against
`data/raw/twcs.csv` (2,811,774 rows) for six candidate brands; heuristic summary at
[`outputs/gate/gate_summary.csv`](outputs/gate/gate_summary.csv). Brand selection is
pending human hand-labelling of [`outputs/gate/gate_sample.csv`](outputs/gate/gate_sample.csv) —
no brand has been picked yet.

## Setup

```bash
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

Raw data goes at `data/raw/twcs.csv` (gitignored, ~500MB — never committed).

## Non-negotiable guardrails

- Safety checks are deterministic (regex/rules), never model-mediated.
- No code path may return `auto_handle` on a failure — every fallback escalates.
- Golden-set labels are hand-labelled by a human, never by the model.
- Thresholds live in [`config/policy.yaml`](config/policy.yaml), never hardcoded.

See [`CLAUDE.md`](CLAUDE.md) and [`DECISIONS.md`](DECISIONS.md) for full working
rules and the running decision log.
