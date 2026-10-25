"""Join a user-supplied intake table to collected descriptions, entirely offline.

No search profile or source inventory is bundled. Exact source URL takes
precedence. Company/title matches are review candidates, never proof that two
records describe the same requisition. Missing and ambiguous rows stay visible.
"""

import argparse
import csv
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from filter_jobs import load_criteria, read_postings, score

SUFFIX = re.compile(r"(?i)\b(inc|incorporated|corp|corporation|co|company|llc|llp|ltd|limited)\b\.?")


def norm_co(name):
    value = SUFFIX.sub(" ", (name or "").casefold())
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", value).split())


def norm_title(title):
    value = (title or "").casefold()
    value = re.sub(r"\(.*?\)", " ", value)
    value = re.sub(r"\b(req\s*\d+|job\s*id\s*\d+)\b", " ", value)
    value = re.sub(r"\bsr\.?\s", "senior ", value)
    value = re.sub(r"\bjr\.?\s", "junior ", value)
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", value).split())


def title_sim(first, second):
    """Token overlap over shorter title; a candidate heuristic, not verification."""
    left, right = set(norm_title(first).split()), set(norm_title(second).split())
    return len(left & right) / min(len(left), len(right)) if left and right else 0


def safe_url(value):
    value = str(value or "").strip()
    try:
        parts = urlsplit(value)
        return value if parts.scheme in ("https", "http") and parts.hostname and not parts.username and not parts.password else ""
    except ValueError:
        return ""


def dedupe_postings(records):
    """Prefer complete observations of the same URL, retaining different URLs."""
    best = {}
    for index, original in enumerate(records):
        record = dict(original)
        record["url"] = safe_url(record.get("url"))
        # Without a URL there is no stable requisition identity. Preserve both
        # observations so the reader can decide whether they are duplicates.
        key = record["url"] or ("no-url", index)
        current = best.get(key)
        def rank(item):
            text = item.get("description", "") or ""
            return bool(text), bool(item.get("location")), len(text)
        if current is None or rank(record) > rank(current):
            best[key] = record
    return list(best.values())


def read_intake(path):
    if not path:
        return []
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t" if Path(path).suffix.lower() == ".tsv" else ","))


def join_records(intake, fetched, criteria=None, fuzzy_threshold=0.7):
    """Retain every intake row, then append fetched rows not used by a match."""
    rules = criteria if criteria is not None else load_criteria()
    fetched = dedupe_postings(fetched)
    by_url = {r["url"]: r for r in fetched if r.get("url")}
    used, output = set(), []

    def combined(base, match, confidence, candidates=0):
        record = dict(base)
        record["intake_url"] = safe_url(base.get("url", base.get("source_url", "")))
        if match:
            # Keep the intake identity. Candidate text is clearly marked as unverified.
            for key in ("description", "source_excerpt", "checked_at", "role_family", "industry"):
                if match.get(key):
                    record[key] = match[key]
            record["url"] = safe_url(match.get("url"))
            record["matched_title"] = match.get("title", "")
            record["matched_company"] = match.get("company", "")
        record.setdefault("description", "")
        record.setdefault("title", "")
        record.setdefault("company", "")
        record["url"] = safe_url(record.get("url", record.get("source_url", "")))
        record.update(score(record, rules))
        record["match_confidence"] = confidence
        record["candidate_count"] = candidates
        record["status"] = "needs_review"
        output.append(record)

    for original in intake:
        base = dict(original)
        base["url"] = safe_url(base.get("url", base.get("source_url", "")))
        match, confidence, count = None, "unmatched", 0
        if base["url"] in by_url:
            match, confidence, count = by_url[base["url"]], "same-url", 1
        else:
            company = norm_co(base.get("company"))
            candidates = [r for r in fetched if company and norm_co(r.get("company")) == company]
            exact = [r for r in candidates if norm_title(r.get("title")) == norm_title(base.get("title"))]
            if len(exact) == 1:
                match, confidence, count = exact[0], "company-title-candidate", 1
            elif len(exact) > 1:
                confidence, count = "ambiguous-company-title", len(exact)
            else:
                fuzzy = [(title_sim(base.get("title"), r.get("title")), r) for r in candidates if not r.get("exact_target_only")]
                fuzzy = [(similarity, r) for similarity, r in fuzzy if similarity >= fuzzy_threshold]
                fuzzy.sort(key=lambda item: item[0], reverse=True)
                count = len(fuzzy)
                if fuzzy and (len(fuzzy) == 1 or fuzzy[0][0] > fuzzy[1][0]):
                    match, confidence = fuzzy[0][1], "fuzzy-title-candidate"
                elif fuzzy:
                    confidence = "ambiguous-fuzzy-title"
        if match:
            used.add(id(match))
        combined(base, match, confidence, count)
    for record in fetched:
        if id(record) not in used:
            combined(record, None, "collected-only")
    return sorted(output, key=lambda r: (not r["passes_criteria"], -r["score"]))


FIELDS = ["title", "company", "location", "url", "role_family", "industry", "checked_at",
          "source_excerpt", "description", "status", "match_confidence", "candidate_count",
          "intake_url", "matched_title", "matched_company", "score", "passes_criteria", "criteria_reasons",
          "signal_tags", "work_mode", "yoe", "comp", "qualifying_quote", "open_questions"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postings", nargs="+", required=True, help="Explicit local collector/import JSON files")
    parser.add_argument("--intake", help="Optional CSV/TSV with title, company, location and url")
    parser.add_argument("--criteria", help="Optional JSON rules; no config includes all with score zero")
    parser.add_argument("--fuzzy-threshold", type=float, default=0.7)
    parser.add_argument("--output", default="local-data/combined.csv")
    args = parser.parse_args()
    if not 0 < args.fuzzy_threshold <= 1:
        parser.error("--fuzzy-threshold must be greater than zero and at most one")
    rows = join_records(read_intake(args.intake), read_postings(args.postings),
                        load_criteria(args.criteria), args.fuzzy_threshold)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({**row, "open_questions": json.dumps(row.get("open_questions", []), ensure_ascii=False)}
                         for row in rows)
    print(f"{len(rows)} rows -> {output}; all require source verification")


if __name__ == "__main__":
    main()
