"""Neutral evidence helpers. No location preferences, applicant profile or industry targets."""

import re


def work_mode(title, location, text):
    """Heuristic only: hybrid wins over a mixed office/remote phrase."""
    head = " ".join((title or "", location or "", (text or "")[:2500]))
    if re.search(r"(?i)\bhybrid\b", head):
        return "hybrid"
    if re.search(r"(?i)\bremote\b|work from anywhere|fully distributed", head):
        return "remote"
    if re.search(r"(?i)\b(on[- ]?site|in[- ]office|in[- ]person)\b", head):
        return "onsite"
    return "unclear"


def parse_yoe(value):
    """Parse the scorer's explicit minimum/range; no cutoff is applied."""
    match = re.fullmatch(r"(\d+)(?:-(\d+)|\+)?", (value or "").strip())
    return (int(match[1]), int(match[2]) if match[2] else None) if match else (None, None)
