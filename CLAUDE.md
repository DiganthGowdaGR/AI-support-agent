# CLAUDE.md

Project context for Claude Code. Read this before any task in this repo.

## What this is

A take-home assignment: an AI customer-support agent for one brand from the Kaggle
"Customer Support on Twitter" dataset. It classifies an inbound tweet, drafts a grounded
reply, and decides auto-handle vs escalate.

**The assignment is graded on the evaluation, not the agent.** A mediocre agent with
rigorous, self-critical evidence beats a clever agent with vague claims. Prioritise
accordingly in every tradeoff.

## Design docs — read before writing code

All in `docs-skills/`. These are the spec. Do not contradict them; if a doc seems wrong,
say so and wait, don't silently deviate.

| Doc | What it governs |
|---|---|
| `PRD.md` | I/O contract, scope, pre-registered targets, acceptance checklist |
| `ARCHITECTURE.md` | Module boundaries, data flow, caching, tech choices |
| `AGENT_POLICY.md` | Hard rules, thresholds, forbidden content, fallback ladder |
| `SKILLS.md` | Per-capability contracts and failure modes |
| `TESTING.md` | Test strategy, leakage assertions, CI |
| `plan.md` | Phase order and schedule |

## Build order — one phase at a time

Do not scaffold ahead. Do not create files for a later phase.

1. **Day 0** — deflection gate, brand selection *(current)*
2. Data pipeline + thread reconstruction + drop report
3. Intent taxonomy + labelling guide
4. Golden set (hand-labelled by the human, not by you)
5. Baselines B0/B1/B2
6. Agent stages S1–S6
7. Eval harness + judge + judge validation
8. Failure analysis, report, decision log

## Working rules

- **Explainability over cleverness.** I will be asked to explain this code live. Prefer
  obvious code over compact code. No metaprogramming, no clever one-liners.
- **Small diffs.** One module or one concern per change. Stop and let me read it.
- **Seed everything.** `SEED=42` from config. No unseeded randomness anywhere.
- **Thresholds live in `config/policy.yaml`**, never hardcoded in logic.
- **Cite borrowed code.** Any snippet, prompt pattern, or approach taken from a blog,
  paper, or library example gets a comment with the source, and a line in `DECISIONS.md`.
- **Every non-obvious choice** gets appended to `DECISIONS.md` as you make it. Do not
  reconstruct these at the end.
- **Never write the golden set labels.** The human labels those. If asked to, refuse —
  a model-labelled eval set measured against a model is circular and worthless.

## Stop and ask before

- Adding a dependency not already in `requirements.txt`
- Changing any threshold in `config/policy.yaml` after test-split results exist
- Deviating from the `AgentOutput` schema in `PRD.md` §FR-4
- Any design decision not covered by the docs

## Guardrails that are not negotiable

- Safety checks are deterministic (regex/rules), never model-mediated. See `AGENT_POLICY.md` §2.
- **No code path may return `auto_handle` on a failure.** Every fallback escalates.
- Leakage prevention is assertions, not discipline: golden-set IDs excluded from the
  retrieval corpus, few-shots from the dev split only, test split gated behind
  `outputs/dev_frozen.lock`.
- Quality metrics never gate CI.

## Environment

- Python 3.11, `venv`, `requirements.txt`
- Raw data at `data/raw/twcs.csv` (gitignored, ~500MB — never commit it)
- Committed artifacts: seeded subsample, embeddings, LLM cache, golden set
- API keys via env var only
