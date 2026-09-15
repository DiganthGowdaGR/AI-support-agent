"""
Phase 1 data pipeline for the SpotifyCares support agent (see DECISIONS.md #8
for the brand choice). Implements docs-skills/ARCHITECTURE.md section A:

    twcs.csv -> brand_tweets -> threads -> pairs -> corpus.parquet

Thread reconstruction (the "sneaky-hard part" per ARCHITECTURE.md) resolves
three cases explicitly:

  1. Brand replies split across multiple tweets: a SpotifyCares reply tweet
     whose own parent is ALSO a SpotifyCares tweet is a continuation, not a
     new reply. We walk backward through same-brand parents to find the
     "head" of the chain, then concatenate the whole chain in timestamp order.
  2. Customers replying to themselves: once we reach the brand reply's
     customer-side parent, we keep walking backward through the customer's
     OWN earlier tweets (same author, inbound) to find the root tweet that
     actually started the conversation.
  3. Orphans: if the backward walk ever hits a tweet_id that isn't in the
     dump, we cannot ground the reply in a customer message. Dropped and
     counted, never silently discarded (ARCHITECTURE.md: "silent row loss is
     how eval sets quietly become unrepresentative").

Usage:
    python src/build_dataset.py
"""

import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml
from datasketch import MinHash, MinHashLSH
from langdetect import DetectorFactory, LangDetectException, detect

BRAND = "SpotifyCares"
RAW_PATH = Path("data/raw/twcs.csv")
CORPUS_PATH = Path("data/processed/corpus.parquet")
DROP_REPORT_PATH = Path("outputs/drop_report.json")
CONFIG_PATH = Path("config/policy.yaml")

# Ported from scripts/00_deflection_gate.py so src/ doesn't import scripts/.
# Known reliability caveat: only 40.2% agreement with hand/LLM labels on this
# brand's replies (DECISIONS.md #6-#7). Kept as a cheap, inspectable tag only
# — never used to drop rows (config: drop_deflections, default off).
DEFLECTION_PATTERNS = [
    r"\bDM\b", r"\bDMs\b", r"direct message", r"\bPM us\b",
    r"message us", r"send us a", r"shoot us a", r"drop us a",
    r"email us", r"contact us", r"call us", r"give us a call",
    r"fill (out|in)", r"follow (us )?(and|so)", r"reach out to us",
]
SUBSTANTIVE_PATTERNS = [
    r"\btry\b", r"\btap\b", r"\bgo to\b", r"\bsettings\b", r"\brestart\b",
    r"\breinstall\b", r"\bupdate\b", r"\blog ?out\b", r"\bsign ?out\b",
    r"\bcheck\b", r"\bmake sure\b", r"\bturn (on|off)\b", r"\btoggle\b",
    r"\bclear (the )?cache\b", r"\buninstall\b", r"\benable\b", r"\bdisable\b",
    r"\byou can\b", r"\bhere's how\b", r"\bthis happens when\b",
]
DEFLECTION_RE = re.compile("|".join(DEFLECTION_PATTERNS), re.I)
SUBSTANTIVE_RE = re.compile("|".join(SUBSTANTIVE_PATTERNS), re.I)

HANDLE_RE = re.compile(r"@\w+")
URL_RE = re.compile(r"https?://\S+")
WHITESPACE_RE = re.compile(r"\s+")
CONTENT_TOKEN_RE = re.compile(r"<url>|__email__")
PUNCT_ONLY_RE = re.compile(r"^[\s\W_]*$")


def classify_heuristic(text: str) -> str:
    if SUBSTANTIVE_RE.search(text):
        return "substantive"
    if DEFLECTION_RE.search(text):
        return "deflection"
    if len(text.split()) < 12:
        return "deflection"
    return "unclear"


def clean_text(text: str) -> str:
    text = HANDLE_RE.sub("", text)
    text = URL_RE.sub("<url>", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def is_content_free(cleaned_text: str) -> bool:
    """True if nothing but <url>/__email__ placeholders and punctuation
    survive cleaning — e.g. a tweet that was just a link. These carry no
    language to detect, so they belong in empty_after_clean, not
    non_english (a placeholder is not a foreign-language sentence)."""
    remainder = CONTENT_TOKEN_RE.sub("", cleaned_text)
    return bool(PUNCT_ONLY_RE.match(remainder))


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_tweet_index(path: Path):
    """Full twcs.csv, indexed for O(1) parent lookups by tweet_id."""
    df = pd.read_csv(
        path,
        dtype=str,
        usecols=["tweet_id", "author_id", "inbound", "created_at", "text", "in_response_to_tweet_id"],
    )
    df["inbound"] = df["inbound"].str.lower().eq("true")
    df["created_at_parsed"] = pd.to_datetime(df["created_at"], format="%a %b %d %H:%M:%S %z %Y")
    pos_of = dict(zip(df["tweet_id"].to_numpy(), range(len(df))))
    cols = {c: df[c].to_numpy() for c in ["tweet_id", "author_id", "inbound", "created_at_parsed", "text", "in_response_to_tweet_id"]}
    return len(df), pos_of, cols


def get_row(pos_of, cols, tweet_id):
    pos = pos_of.get(tweet_id)
    if pos is None:
        return None
    return {c: cols[c][pos] for c in cols}


def find_continuation_head(pos_of, cols, tid, brand):
    """Walk backward through same-brand parents to the head of a reply chain."""
    seen = set()
    while True:
        row = get_row(pos_of, cols, tid)
        parent_id = row["in_response_to_tweet_id"]
        if pd.isna(parent_id):
            return tid
        parent = get_row(pos_of, cols, parent_id)
        if parent is None or parent["author_id"] != brand or parent["inbound"]:
            return tid
        if parent_id in seen:  # defensive cycle guard; shouldn't occur in real data
            return tid
        seen.add(parent_id)
        tid = parent_id


def find_customer_root(pos_of, cols, customer_tid):
    """Walk backward through a customer's own self-replies to the thread root."""
    seen = set()
    tid = customer_tid
    while True:
        row = get_row(pos_of, cols, tid)
        parent_id = row["in_response_to_tweet_id"]
        if pd.isna(parent_id):
            return tid
        parent = get_row(pos_of, cols, parent_id)
        if parent is None or parent["author_id"] != row["author_id"] or not parent["inbound"]:
            return tid
        if parent_id in seen:
            return tid
        seen.add(parent_id)
        tid = parent_id


def build_reply_groups(pos_of, cols, brand):
    """One row per distinct brand-reply chain, resolved to its root customer tweet."""
    brand_tweet_ids = [
        cols["tweet_id"][i] for i in range(len(cols["tweet_id"]))
        if cols["author_id"][i] == brand and not cols["inbound"][i]
    ]

    heads = {}  # head_tid -> list of member tids (the chain)
    for tid in brand_tweet_ids:
        head = find_continuation_head(pos_of, cols, tid, brand)
        heads.setdefault(head, []).append(tid)

    drop_reasons = Counter()
    groups = []
    for head_tid, members in heads.items():
        head_row = get_row(pos_of, cols, head_tid)
        parent_id = head_row["in_response_to_tweet_id"]
        if pd.isna(parent_id):
            drop_reasons["orphan_missing_parent"] += 1
            continue
        parent = get_row(pos_of, cols, parent_id)
        if parent is None:
            drop_reasons["orphan_missing_parent"] += 1
            continue
        if not parent["inbound"]:
            drop_reasons["parent_not_customer"] += 1
            continue

        root_id = find_customer_root(pos_of, cols, parent_id)
        member_rows = sorted(
            (get_row(pos_of, cols, m) for m in members),
            key=lambda r: (r["created_at_parsed"], r["tweet_id"]),
        )
        brand_reply_raw = " ".join(r["text"] for r in member_rows)
        groups.append({
            "root_customer_id": root_id,
            "brand_reply_tweet_ids": ",".join(r["tweet_id"] for r in member_rows),
            "brand_reply_created_at": member_rows[0]["created_at_parsed"],
            "brand_reply_raw": brand_reply_raw,
        })

    # Collapse branching: keep only the earliest brand-reply group per root.
    groups.sort(key=lambda g: (g["root_customer_id"], g["brand_reply_created_at"], g["brand_reply_tweet_ids"]))
    by_root = {}
    for g in groups:
        if g["root_customer_id"] not in by_root:
            by_root[g["root_customer_id"]] = g
        else:
            drop_reasons["duplicate_thread_same_root"] += 1

    pairs = []
    for root_id, g in by_root.items():
        root_row = get_row(pos_of, cols, root_id)
        pairs.append({
            "customer_tweet_id": root_id,
            "customer_created_at": root_row["created_at_parsed"],
            "customer_text_raw": root_row["text"],
            "brand_reply_tweet_ids": g["brand_reply_tweet_ids"],
            "brand_reply_created_at": g["brand_reply_created_at"],
            "brand_reply_raw": g["brand_reply_raw"],
        })

    return pairs, drop_reasons, len(heads)


def detect_english(text: str) -> bool:
    try:
        return detect(text) == "en"
    except LangDetectException:
        return False


def remove_near_duplicates(df: pd.DataFrame, seed: int, threshold: float):
    """MinHash LSH near-dup removal on cleaned customer text. Deterministic
    processing order (sorted by tweet_id) so repeated runs drop the same
    rows every time."""
    df = df.sort_values("customer_tweet_id", kind="stable").reset_index(drop=True)
    lsh = MinHashLSH(threshold=threshold, num_perm=128)
    keep_mask = []
    for i, row in df.iterrows():
        shingles = {
            " ".join(w) for w in zip(*[row["customer_text_clean"].lower().split()[j:] for j in range(3)])
        } or {row["customer_text_clean"].lower()}
        mh = MinHash(num_perm=128, seed=seed)
        for s in shingles:
            mh.update(s.encode("utf-8"))
        is_dup = len(lsh.query(mh)) > 0
        keep_mask.append(not is_dup)
        if not is_dup:
            lsh.insert(str(row["customer_tweet_id"]), mh)
    return df[keep_mask].reset_index(drop=True), int(len(df) - sum(keep_mask))


def main():
    config = load_config()
    seed = config["SEED"]
    DetectorFactory.seed = seed

    print(f"Loading {RAW_PATH} ...")
    n_total_rows, pos_of, cols = load_tweet_index(RAW_PATH)
    print(f"  {n_total_rows:,} total rows in twcs.csv")

    pairs, group_drop_reasons, n_reply_groups = build_reply_groups(pos_of, cols, BRAND)
    input_rows = n_reply_groups  # every distinct brand-reply chain identified, before dedup collapse
    print(f"  {n_reply_groups:,} distinct {BRAND} reply chains identified (input_rows)")

    df = pd.DataFrame(pairs)
    drop_reasons = Counter(group_drop_reasons)

    df["customer_text_clean"] = df["customer_text_raw"].apply(clean_text)
    df["brand_reply_clean"] = df["brand_reply_raw"].apply(clean_text)

    # Content-free customer text (just a URL/redaction placeholder) has no
    # language to detect — route it here, not into non_english, so the drop
    # report's reason codes stay accurate (they're evidence, not just counts).
    empty_mask = (
        (df["customer_text_clean"] == "")
        | (df["brand_reply_clean"] == "")
        | df["customer_text_clean"].apply(is_content_free)
    )
    drop_reasons["empty_after_clean"] += int(empty_mask.sum())
    df = df[~empty_mask].reset_index(drop=True)
    n_after_clean = len(df)

    # langdetect is unreliable under lang_min_words (diagnostic: 19/30 sampled
    # non_english drops were unambiguously English, nearly all short). Below
    # the floor we keep the row and flag it rather than guess wrong silently.
    word_count = df["customer_text_clean"].str.split().str.len()
    is_short = word_count < config["lang_min_words"]
    df["lang_uncertain"] = is_short

    checked_is_english = df.loc[~is_short, "customer_text_clean"].apply(detect_english)
    non_english_mask = pd.Series(False, index=df.index)
    non_english_mask.loc[~is_short] = ~checked_is_english

    drop_reasons["non_english"] += int(non_english_mask.sum())
    df = df[~non_english_mask].reset_index(drop=True)
    n_after_lang = len(df)
    n_lang_uncertain = int(df["lang_uncertain"].sum())

    df, n_near_dup = remove_near_duplicates(df, seed, config["near_dup_jaccard_threshold"])
    drop_reasons["near_duplicate"] += n_near_dup
    n_after_dedup = len(df)

    df["deflection_tag"] = df["brand_reply_clean"].apply(classify_heuristic)

    if config["drop_deflections"]:
        deflect_mask = df["deflection_tag"] == "deflection"
        drop_reasons["deflection_filtered"] += int(deflect_mask.sum())
        df = df[~deflect_mask].reset_index(drop=True)

    df = df.sort_values(["customer_tweet_id"], kind="stable").reset_index(drop=True)

    kept = len(df)
    reconciled_total = kept + sum(drop_reasons.values())
    assert reconciled_total == input_rows, (
        f"Drop report does not reconcile: kept({kept}) + dropped({sum(drop_reasons.values())}) "
        f"= {reconciled_total} != input_rows({input_rows})"
    )

    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    output_cols = [
        "customer_tweet_id", "customer_created_at", "customer_text_raw", "customer_text_clean",
        "brand_reply_tweet_ids", "brand_reply_created_at", "brand_reply_raw", "brand_reply_clean",
        "deflection_tag", "lang_uncertain",
    ]
    df[output_cols].to_parquet(CORPUS_PATH, index=False)

    DROP_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    drop_report = {
        "brand": BRAND,
        "seed": seed,
        "input_rows": input_rows,
        "kept": kept,
        "dropped_by_reason": dict(sorted(drop_reasons.items())),
        "reconciliation_check": f"{kept} + {sum(drop_reasons.values())} == {input_rows}",
    }
    with open(DROP_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(drop_report, f, indent=2)

    print()
    print("=== Pipeline summary ===")
    print(f"{'stage':30s} {'rows':>10s}")
    print(f"{'twcs.csv total rows':30s} {n_total_rows:>10,}")
    print(f"{'brand reply chains (input)':30s} {input_rows:>10,}")
    print(f"{'after clean (non-empty)':30s} {n_after_clean:>10,}")
    print(f"{'after langdetect==en':30s} {n_after_lang:>10,}   (of which lang_uncertain: {n_lang_uncertain:,})")
    print(f"{'after near-dup removal':30s} {n_after_dedup:>10,}   (removed {n_near_dup:,})")
    print(f"{'final kept (corpus.parquet)':30s} {kept:>10,}")
    print()
    print("Dropped by reason:")
    for reason, count in sorted(drop_reasons.items()):
        print(f"  {reason:30s} {count:>10,}")
    print()
    print(f"Reconciliation: kept({kept}) + dropped({sum(drop_reasons.values())}) == input_rows({input_rows}) -> OK")
    print(f"Wrote {CORPUS_PATH} and {DROP_REPORT_PATH}")


if __name__ == "__main__":
    main()
