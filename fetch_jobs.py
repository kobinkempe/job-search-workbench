"""Pull job postings (with full descriptions) from public, keyless ATS APIs.

Greenhouse / Lever / Ashby all publish job boards as JSON with no auth.
We try each token against all three, keep whatever resolves, and cache the
raw payload to disk so re-filtering later costs zero network calls.

Usage: python fetch_jobs.py --seeds local-config/seeds.json
Supply your own board tokens. No employers or targets are bundled.
Output: local-data/cache/raw_<token>.json and index.json
"""

import argparse
import html
import json
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from companies import load_seeds

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local-data", "cache")
VERTICAL_OF = {}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

ENDPOINTS = [
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{t}/jobs?content=true"),
    ("lever",      "https://api.lever.co/v0/postings/{t}?mode=json"),
    ("ashby",      "https://api.ashbyhq.com/posting-api/job-board/{t}?includeCompensation=true"),
]


def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def strip_html(s):
    """Unescape entities BEFORE stripping tags.

    Greenhouse returns descriptions with tags HTML-escaped (&lt;li&gt;).
    Stripping first left those escapes intact, then unescaping turned them
    back into live tags - so raw markup ended up in the extracted text and
    corrupted every downstream regex match.
    """
    if not s:
        return ""
    s = html.unescape(html.unescape(s))          # twice: some feeds double-encode
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)                          # entities revealed by tag removal
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", s)).strip()


def normalize(source, token, payload):
    """Flatten the three very different response shapes into one record type."""
    out = []
    if source == "greenhouse":
        for j in payload.get("jobs", []):
            out.append({
                "title": j.get("title", ""),
                "location": (j.get("location") or {}).get("name", ""),
                "url": j.get("absolute_url", ""),
                "updated": j.get("updated_at", ""),
                "description": strip_html(j.get("content", "")),
                "raw_comp": None,
            })
    elif source == "lever":
        for j in payload if isinstance(payload, list) else []:
            cats = j.get("categories") or {}
            out.append({
                "title": j.get("text", ""),
                "location": cats.get("location", "") or "",
                "url": j.get("hostedUrl", "") or j.get("applyUrl", ""),
                "updated": j.get("createdAt", ""),
                "description": strip_html(j.get("descriptionPlain") or j.get("description", "")),
                "raw_comp": cats.get("commitment"),
            })
    elif source == "ashby":
        for j in payload.get("jobs", []):
            comp = j.get("compensation") or {}
            out.append({
                "title": j.get("title", ""),
                "location": j.get("location", "") or "",
                "url": j.get("jobUrl", "") or j.get("applyUrl", ""),
                "updated": j.get("publishedAt", ""),
                "description": strip_html(j.get("descriptionHtml") or j.get("descriptionPlain", "")),
                "raw_comp": json.dumps(comp) if comp else None,
            })
    for r in out:
        r["company_token"] = token
        r["source"] = source
        r["vertical"] = VERTICAL_OF.get(token, "unknown")
    return out


def probe(token):
    for source, tmpl in ENDPOINTS:
        try:
            payload = get(tmpl.format(t=token))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                json.JSONDecodeError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("status") == 404:
            continue
        jobs = normalize(source, token, payload)
        if jobs:
            return source, jobs
    return None, []


def main():
    global VERTICAL_OF, CACHE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", required=True, help="JSON category: [board-token] inventory")
    parser.add_argument("--output-dir", default=CACHE)
    args = parser.parse_args()
    all_tokens, VERTICAL_OF = load_seeds(args.seeds)
    CACHE = args.output_dir
    os.makedirs(CACHE, exist_ok=True)
    index, total = {}, 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for token, (source, jobs) in zip(all_tokens, pool.map(probe, all_tokens)):
            if not jobs:
                continue
            index[token] = {"source": source, "count": len(jobs),
                            "vertical": VERTICAL_OF.get(token, "unknown")}
            total += len(jobs)
            with open(os.path.join(CACHE, "raw_%s.json" % token), "w", encoding="utf-8") as f:
                json.dump(jobs, f, ensure_ascii=False)
            print("  %-24s %-11s %4d jobs" % (token, source, len(jobs)))
    with open(os.path.join(CACHE, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1)
    print("\nResolved %d/%d company boards, %d postings cached."
          % (len(index), len(all_tokens), total))


if __name__ == "__main__":
    main()
