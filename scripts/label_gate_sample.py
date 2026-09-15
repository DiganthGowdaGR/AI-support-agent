"""
Interactive hand-labelling helper for outputs/gate/gate_sample.csv.

Never displays the `heuristic` column - the rubric requires labelling blind to it.
Writes outputs/gate/gate_sample_labelled.csv after every row, so Ctrl+C / closing
the terminal loses nothing; re-running skips rows already labelled.

Usage: python scripts/label_gate_sample.py
"""

import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")  # rubric has non-ASCII em dashes; cp1252 mangles them
SRC = Path("outputs/gate/gate_sample.csv")
DST = Path("outputs/gate/gate_sample_labelled.csv")
RUBRIC = Path("deflection_labelling_rubric.md")
LABELS = {"s": "substantive", "d": "deflection", "u": "unclear"}
CONF = {"h": "high", "l": "low"}

try:
    import msvcrt
    def get_key() -> str:
        return msvcrt.getch().decode("utf-8", "ignore").lower()
except ImportError:
    def get_key() -> str:
        return (input() or " ")[0].lower()


def print_rubric() -> None:
    text = RUBRIC.read_text(encoding="utf-8")
    start = text.index("## Boundary rules")
    end = text.index("## Process")
    print(text[start:end].strip())
    print("\n" + "=" * 70)


def load() -> pd.DataFrame:
    df = pd.read_csv(SRC, dtype=str).fillna("")
    for col in ("label_rationale", "confidence"):
        if col not in df.columns:
            df[col] = ""
    if DST.exists():
        done = pd.read_csv(DST, dtype=str).fillna("").set_index("tweet_id")
        for col in ("hand_label", "label_rationale", "confidence"):
            df[col] = df["tweet_id"].map(done[col]).fillna(df[col])
    return df.sort_values("brand", kind="stable").reset_index(drop=True)


def prompt_choice(prompt: str, options: dict) -> str:
    print(prompt, end=" ", flush=True)
    while True:
        key = get_key()
        if key in options:
            print(options[key])
            return options[key]


def main() -> None:
    print_rubric()
    df = load()
    df.to_csv(DST, index=False)

    labelled = df["hand_label"] != ""
    n_labelled, n_substantive = labelled.sum(), (df["hand_label"] == "substantive").sum()
    brands = df["brand"].unique().tolist()

    for bi, brand in enumerate(brands, start=1):
        rows = df[df["brand"] == brand]
        for ri, idx in enumerate(rows.index, start=1):
            if df.at[idx, "hand_label"]:
                continue
            pct = round(100 * n_substantive / n_labelled, 1) if n_labelled else 0.0
            print(f"\nbrand {bi}/{len(brands)}, row {ri}/{len(rows)}, {pct}% substantive so far")
            print("-" * 70)
            print(f"CUSTOMER: {df.at[idx, 'customer_text']}")
            print(f"REPLY:    {df.at[idx, 'brand_reply']}")
            label = prompt_choice("Label [s]ubstantive/[d]eflection/[u]nclear:", LABELS)
            rationale = input("Rationale (blank to skip): ").strip()
            confidence = prompt_choice("Confidence [h]igh/[l]ow:", CONF)

            df.at[idx, "hand_label"] = label
            df.at[idx, "label_rationale"] = rationale
            df.at[idx, "confidence"] = confidence
            df.to_csv(DST, index=False)

            n_labelled += 1
            n_substantive += label == "substantive"

    print("\nAll rows labelled.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nProgress saved. Resume anytime - already-labelled rows are skipped.")
        sys.exit(0)
