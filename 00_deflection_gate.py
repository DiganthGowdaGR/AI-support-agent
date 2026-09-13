"""
Day-0 brand selection gate.

The whole assignment depends on one question: do this brand's support replies contain
actual substance, or do they just say "DM us"? A brand that deflects everything gives
you nothing to ground a draft reply in, and the retrieval half of the system becomes
decoration.

This script does two things per candidate brand:
  1. A cheap heuristic estimate of the deflection rate.
  2. A sample exported to CSV for the human to hand-label.

The heuristic is NOT the answer. It is a pre-screen. You hand-label 40 per brand,
compare against the heuristic, and report both. If the heuristic disagrees with your
hand labels badly, that is itself worth a line in DECISIONS.md - it is a small,
honest demonstration that you check your own instruments before trusting them.

Usage:
    python scripts/00_deflection_gate.py --data data/raw/twcs.csv
    # then hand-label outputs/gate/gate_sample.csv (fill the `hand_label` column)
    python scripts/00_deflection_gate.py --score outputs/gate/gate_sample.csv
"""

import argparse
import re
from pathlib import Path

import pandas as pd

SEED = 42
CHUNK = 250_000

# Candidate brands. Chosen for volume + plausibly step-heavy support domains.
# Deliberately includes two expected to score badly (Amazon, Apple), so the gate has
# a real negative control rather than only confirming the brand I already prefer.
CANDIDATES = [
    "SpotifyCares",
    "TMobileHelp",
    "Ask_Spectrum",
    "AppleSupport",
    "AmazonHelp",
    "Uber_Support",
]

# Phrases that redirect the customer somewhere else instead of helping in-channel.
DEFLECTION_PATTERNS = [
    r"\bDM\b", r"\bDMs\b", r"direct message", r"\bPM us\b",
    r"message us", r"send us a", r"shoot us a", r"drop us a",
    r"email us", r"contact us", r"call us", r"give us a call",
    r"fill (out|in)", r"follow (us )?(and|so)", r"reach out to us",
]

# Markers of an actual instruction or answer.
SUBSTANTIVE_PATTERNS = [
    r"\btry\b", r"\btap\b", r"\bgo to\b", r"\bsettings\b", r"\brestart\b",
    r"\breinstall\b", r"\bupdate\b", r"\blog ?out\b", r"\bsign ?out\b",
    r"\bcheck\b", r"\bmake sure\b", r"\bturn (on|off)\b", r"\btoggle\b",
    r"\bclear (the )?cache\b", r"\buninstall\b", r"\benable\b", r"\bdisable\b",
    r"\byou can\b", r"\bhere's how\b", r"\bthis happens when\b",
]

DEFLECTION_RE = re.compile("|".join(DEFLECTION_PATTERNS), re.I)
SUBSTANTIVE_RE = re.compile("|".join(SUBSTANTIVE_PATTERNS), re.I)


def classify_heuristic(text: str) -> str:
    """Rough three-way bucket. Substance wins ties: a reply that gives a real step AND
    offers a DM as backup is still substantive."""
    if SUBSTANTIVE_RE.search(text):
        return "substantive"
    if DEFLECTION_RE.search(text):
        return "deflection"
    if len(text.split()) < 12:
        return "deflection"  # short with no step is almost always an apology
    return "unclear"


def load_brand_replies(path: Path) -> pd.DataFrame:
    """Pass 1: collect outbound replies from candidate brands, plus inbound counts."""
    replies, inbound_counts = [], {b: 0 for b in CANDIDATES}
    cols = ["tweet_id", "author_id", "inbound", "text", "in_response_to_tweet_id"]

    for chunk in pd.read_csv(path, usecols=cols, chunksize=CHUNK, dtype=str):
        chunk["inbound"] = chunk["inbound"].astype(str).str.lower().eq("true")

        out = chunk[
            chunk["author_id"].isin(CANDIDATES)
            & ~chunk["inbound"]
            & chunk["in_response_to_tweet_id"].notna()
        ]
        replies.append(out)

        # How many inbound tweets mention each brand - proxy for total demand.
        inb = chunk[chunk["inbound"]]
        for b in CANDIDATES:
            inbound_counts[b] += inb["text"].str.contains(f"@{b}", case=False, na=False).sum()

    return pd.concat(replies, ignore_index=True), inbound_counts


def attach_parents(path: Path, sample: pd.DataFrame) -> pd.DataFrame:
    """Pass 2: pull the customer tweet each sampled reply was responding to."""
    wanted = set(sample["in_response_to_tweet_id"].dropna())
    found = {}

    for chunk in pd.read_csv(path, usecols=["tweet_id", "text"], chunksize=CHUNK, dtype=str):
        hit = chunk[chunk["tweet_id"].isin(wanted)]
        found.update(dict(zip(hit["tweet_id"], hit["text"])))

    sample["customer_text"] = sample["in_response_to_tweet_id"].map(found)
    return sample


def run_gate(data_path: Path, out_dir: Path, n_per_brand: int = 100) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    replies, inbound_counts = load_brand_replies(data_path)
    replies["heuristic"] = replies["text"].apply(classify_heuristic)

    rows = []
    for brand, grp in replies.groupby("author_id"):
        counts = grp["heuristic"].value_counts()
        total = len(grp)
        rows.append({
            "brand": brand,
            "reply_count": total,
            "inbound_mentions": inbound_counts.get(brand, 0),
            "reply_rate": round(total / max(inbound_counts.get(brand, 1), 1), 3),
            "substantive_%": round(100 * counts.get("substantive", 0) / total, 1),
            "deflection_%": round(100 * counts.get("deflection", 0) / total, 1),
            "unclear_%": round(100 * counts.get("unclear", 0) / total, 1),
        })

    summary = pd.DataFrame(rows).sort_values("substantive_%", ascending=False)
    summary.to_csv(out_dir / "gate_summary.csv", index=False)
    print("\nHEURISTIC ESTIMATE (pre-screen only - hand-label before trusting):\n")
    print(summary.to_string(index=False))

    # Stratified sample so hand-labelling sees all three buckets per brand, not just
    # the dominant one. Unstratified sampling would make rare substantive replies
    # invisible at a brand that mostly deflects.
    picks = []
    for brand, grp in replies.groupby("author_id"):
        per_bucket = max(n_per_brand // 3, 1)
        for bucket, sub in grp.groupby("heuristic"):
            picks.append(sub.sample(min(per_bucket, len(sub)), random_state=SEED))

    sample = pd.concat(picks, ignore_index=True)
    sample = attach_parents(data_path, sample)
    sample["hand_label"] = ""  # you fill this: substantive | deflection | unclear

    sample = sample[[
        "author_id", "tweet_id", "customer_text", "text", "heuristic", "hand_label"
    ]].rename(columns={"author_id": "brand", "text": "brand_reply"})

    sample.sample(frac=1, random_state=SEED).to_csv(out_dir / "gate_sample.csv", index=False)

    print(f"\nWrote {len(sample)} rows to {out_dir/'gate_sample.csv'}")
    print("Hand-label at least 40 per brand in the `hand_label` column, then run --score.")
    print("Label blind: sort by brand, ignore the `heuristic` column while labelling.\n")


def score_labels(labelled_path: Path) -> None:
    """Compare hand labels against the heuristic. Both numbers go in the report."""
    df = pd.read_csv(labelled_path)
    df = df[df["hand_label"].notna() & (df["hand_label"].astype(str).str.strip() != "")]
    if df.empty:
        print("No hand labels found. Fill the `hand_label` column first.")
        return

    print(f"\nHand-labelled: {len(df)} rows\n")
    print("SUBSTANTIVE RATE BY BRAND (hand labels - this is the real number):\n")
    rate = (
        df.assign(is_sub=df["hand_label"].str.strip().eq("substantive"))
          .groupby("brand")["is_sub"]
          .agg(["mean", "count"])
          .rename(columns={"mean": "substantive_rate", "count": "n"})
          .sort_values("substantive_rate", ascending=False)
    )
    rate["substantive_rate"] = (100 * rate["substantive_rate"]).round(1)
    print(rate.to_string())

    agreement = (df["heuristic"] == df["hand_label"].str.strip()).mean()
    print(f"\nHeuristic vs hand agreement: {agreement:.1%}")
    if agreement < 0.70:
        print("Low agreement - the heuristic is unreliable. Report hand labels only,")
        print("and note the disagreement in DECISIONS.md.")
    print()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("data/raw/twcs.csv"))
    p.add_argument("--out", type=Path, default=Path("outputs/gate"))
    p.add_argument("--score", type=Path, help="Path to the hand-labelled gate_sample.csv")
    args = p.parse_args()

    if args.score:
        score_labels(args.score)
    else:
        run_gate(args.data, args.out)
