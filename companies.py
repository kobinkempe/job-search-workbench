"""Load an operator-supplied ATS seed inventory; no employer list is bundled."""

import json
import re
from pathlib import Path


def load_seeds(path):
    """JSON object of category: [board-token, ...]; empty example means no requests."""
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Seed inventory must be an object of category: [tokens]")
    vertical_of = {}
    for category, tokens in payload.items():
        if not isinstance(category, str) or not isinstance(tokens, list):
            raise ValueError("Seed inventory must be an object of category: [tokens]")
        for token in tokens:
            if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", token):
                raise ValueError("Board tokens may contain letters, digits, dots, hyphens and underscores")
            if token in vertical_of and vertical_of[token] != category:
                raise ValueError("A token must belong to only one category")
            vertical_of[token] = category
    return sorted(vertical_of), vertical_of
