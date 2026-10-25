"""Export a local combined CSV into the current browser's JSON import schema.

Does not overwrite demo/data.json or viewer/data.json. Every output record is
unverified. Inspect the output before sharing it; local source data is private.
"""

import argparse
import csv
import json
from pathlib import Path
from build_final import safe_url


def import_record(row, index):
    if not all(isinstance(row.get(key), str) and row[key].strip() for key in ("title", "company")):
        raise ValueError(f"Record {index + 1} requires a nonempty title and company")
    questions = row.get("open_questions", [])
    if isinstance(questions, str):
        try:
            questions = json.loads(questions)
        except (ValueError, TypeError):
            questions = [questions] if questions else []
    if not isinstance(questions, list):
        questions = []
    questions = [str(q) for q in questions]
    confidence = row.get("match_confidence", "")
    if confidence not in ("same-url", "collected-only", ""):
        questions.append("Confirm this candidate description belongs to the original intake posting: " + confidence)
        if row.get("matched_title"):
            questions.append("Candidate title at source: " + row["matched_title"])
        if safe_url(row.get("intake_url")):
            questions.append("Compare the original intake URL: " + safe_url(row["intake_url"]))
    questions.append("Confirm the original source, current opening status and each factual claim.")
    return {
        "id": f"local-{index}", "title": row.get("title", ""), "company": row.get("company", ""),
        "role_family": row.get("role_family") or "Unspecified",
        "industry": row.get("industry") or "Unspecified", "status": "needs_review",
        "source_url": safe_url(row.get("url")), "checked_at": row.get("checked_at", ""),
        "source_excerpt": row.get("source_excerpt", ""), "description": row.get("description", ""),
        "open_questions": questions,
    }


def build(combined, output):
    with Path(combined).open(encoding="utf-8-sig", newline="") as stream:
        jobs = [import_record(row, index) for index, row in enumerate(csv.DictReader(stream))]
    if not 1 <= len(jobs) <= 500:
        raise ValueError("Browser imports support 1–500 records; split or complete the collection before exporting")
    payload = json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2)
    if len(payload.encode("utf-8")) > 2_000_000:
        raise ValueError("Browser imports support at most 2 MB; reduce or split the collection")
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload, encoding="utf-8")
    return len(jobs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combined", default="local-data/combined.csv")
    parser.add_argument("--output", default="local-data/research-import.json")
    args = parser.parse_args()
    print(f"{build(args.combined, args.output)} unverified records -> {args.output}")


if __name__ == "__main__":
    main()
