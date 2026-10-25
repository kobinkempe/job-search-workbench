"""Offline scoring with no built-in applicant profile. No config means include all."""

import argparse
import csv
import json
import re
from pathlib import Path
from viewer_tags import work_mode

DEFAULT_CRITERIA = {
    "version": 1, "title_include": [], "title_exclude": [],
    "location_include": [], "location_exclude": [], "work_modes": [],
    "min_required_years": None, "max_required_years": None,
    "include_unknown_experience": True, "weighted_terms": [],
}
YOE_PAT = re.compile(
    r"(?i)\b(\d{1,2})\s*(?:\+|plus)?\s*(?:[-–—]|to)?\s*(\d{1,2})?"
    r"\s*\+?\s*years?(?:\s+(?:of|in|as))?(?:\s+[\w/-]+){0,8}?"
    r"\s+(?:experience|tenure|background|track record)"
)
RANGE_PAT = re.compile(
    r"(?i)\$\s?([\d,]+(?:\.\d+)?)\s*(k)?\s*(?:[-–—]|to)\s*"
    r"\$?\s?([\d,]+(?:\.\d+)?)\s*(k)?"
)
SALARY_CTX = re.compile(
    r"(?i)salary|base pay|base compensation|compensation range|pay range|pay band|annual pay"
)


def load_criteria(path=None):
    """Validate supplied rules; absent config contains no implicit preferences."""
    criteria = {k: (list(v) if isinstance(v, list) else v)
                for k, v in DEFAULT_CRITERIA.items()}
    if path:
        supplied = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(supplied, dict):
            raise ValueError("Criteria must be a JSON object")
        unknown = set(supplied) - set(criteria)
        if unknown:
            raise ValueError("Unknown criteria fields: " + ", ".join(sorted(unknown)))
        criteria.update(supplied)
    if criteria["version"] != 1:
        raise ValueError("Only criteria version 1 is supported")
    for key in ("title_include", "title_exclude", "location_include", "location_exclude"):
        if not isinstance(criteria[key], list) or any(not isinstance(p, str) or not p
                                                    for p in criteria[key]):
            raise ValueError(key + " must be an array of nonempty regex strings")
        for pattern in criteria[key]:
            re.compile(pattern, re.I)
    if not isinstance(criteria["work_modes"], list) or any(
            m not in ("remote", "hybrid", "onsite", "unclear") for m in criteria["work_modes"]):
        raise ValueError("work_modes must contain remote, hybrid, onsite or unclear")
    for key in ("min_required_years", "max_required_years"):
        value = criteria[key]
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(key + " must be a nonnegative integer or null")
    if (criteria["min_required_years"] is not None
            and criteria["max_required_years"] is not None
            and criteria["min_required_years"] > criteria["max_required_years"]):
        raise ValueError("min_required_years cannot exceed max_required_years")
    if type(criteria["include_unknown_experience"]) is not bool:
        raise ValueError("include_unknown_experience must be true or false")
    if not isinstance(criteria["weighted_terms"], list):
        raise ValueError("weighted_terms must be an array")
    for term in criteria["weighted_terms"]:
        if (not isinstance(term, dict) or set(term) != {"label", "pattern", "weight"}
                or not isinstance(term["label"], str) or not term["label"]
                or not isinstance(term["pattern"], str) or not term["pattern"]
                or type(term["weight"]) not in (int, float)):
            raise ValueError("Each weighted term needs label, pattern and numeric weight")
        if not __import__("math").isfinite(term["weight"]):
            raise ValueError("Weight must be finite")
        re.compile(term["pattern"], re.I)
    return criteria


def parse_comp(text):
    """Extract a dollar range near salary language, without currency/period inference.

    Hourly and annual amounts are not converted. A human must confirm currency,
    period and applicability. There is no cost-of-living normalization.
    """
    for match in RANGE_PAT.finditer(text or ""):
        context = (text or "")[max(0, match.start() - 150):match.end() + 100]
        if not SALARY_CTX.search(context):
            continue
        low = float(match[1].replace(",", "")) * (1000 if match[2] else 1)
        high = float(match[3].replace(",", "")) * (1000 if match[4] else 1)
        if 0 < low <= high:
            return int(low), int(high)
    return None


def yoe_of(text):
    """Highest explicit experience minimum plus excerpt, for human review.

    A requirement may describe one skill rather than total career experience.
    This conservative heuristic is not an eligibility decision.
    """
    candidates = []
    for match in YOE_PAT.finditer(text or ""):
        low = int(match[1])
        high = int(match[2]) if match[2] else None
        if high is not None and high < low:
            continue
        start = max((text or "").rfind("\n", 0, match.start()),
                    (text or "").rfind(". ", 0, match.start())) + 1
        end = (text or "").find("\n", match.end())
        excerpt = re.sub(r"\s+", " ", (text or "")[start:end if end >= 0 else match.end() + 180]).strip()
        candidates.append((low, high, excerpt[:500]))
    return max(candidates, key=lambda r: r[0]) if candidates else None


def score(job, criteria=None):
    """Assess every record, retaining rejected rows with their explicit reasons."""
    rules = criteria if criteria is not None else load_criteria()
    title, location = job.get("title", "") or "", job.get("location", "") or ""
    text = job.get("description", job.get("desc", "")) or ""
    reasons = []
    for field, value in (("title", title), ("location", location)):
        included, excluded = rules[field + "_include"], rules[field + "_exclude"]
        if included and not any(re.search(p, value, re.I) for p in included):
            reasons.append(field + " did not match configured include patterns")
        if any(re.search(p, value, re.I) for p in excluded):
            reasons.append(field + " matched a configured exclude pattern")
    mode = work_mode(title, location, text)
    if rules["work_modes"] and mode not in rules["work_modes"]:
        reasons.append("work mode did not match configured choices")
    years = yoe_of(text)
    if years:
        if rules["min_required_years"] is not None and years[0] < rules["min_required_years"]:
            reasons.append("stated experience minimum is below configured lower bound")
        if rules["max_required_years"] is not None and years[0] > rules["max_required_years"]:
            reasons.append("stated experience minimum exceeds configured upper bound")
    elif not rules["include_unknown_experience"]:
        reasons.append("no explicit numeric experience requirement found")
    tags, total = [], 0
    for term in rules["weighted_terms"]:
        if re.search(term["pattern"], title + "\n" + text, re.I):
            total += term["weight"]
            tags.append(term["label"])
    comp = parse_comp(text)
    return {
        "score": total, "passes_criteria": not reasons,
        "criteria_reasons": "; ".join(reasons), "signal_tags": ",".join(tags), "work_mode": mode,
        "yoe": (f"{years[0]}-{years[1]}" if years and years[1] is not None
                else f"{years[0]}+" if years else "not stated"),
        "qualifying_quote": years[2] if years else "",
        "comp": f"${comp[0]:,}-{comp[1]:,}" if comp else "",
    }


def read_postings(paths):
    """Read explicit local JSON files in collector or browser import shape."""
    records = []
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        rows = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError(f"{path}: expected an array of posting objects or a jobs array")
        for row in rows:
            row = dict(row)
            row.setdefault("description", row.get("desc", ""))
            row.setdefault("company", row.get("company_token", ""))
            row.setdefault("url", row.get("source_url", ""))
            records.append(row)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postings", nargs="+", required=True, help="Explicit local JSON files")
    parser.add_argument("--criteria", help="Optional JSON rules; omitted means include all, score zero")
    parser.add_argument("--output", default="local-data/scored.csv")
    args = parser.parse_args()
    rules = load_criteria(args.criteria)
    rows = [dict(job, **score(job, rules)) for job in read_postings(args.postings)]
    rows.sort(key=lambda r: (not r["passes_criteria"], -r["score"]))
    fields = ["title", "company", "location", "url", "score", "passes_criteria",
              "criteria_reasons", "signal_tags", "work_mode", "yoe", "comp", "qualifying_quote"]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} postings assessed; {sum(r['passes_criteria'] for r in rows)} pass configured rules -> {output}")


if __name__ == "__main__":
    main()
