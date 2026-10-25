"""Collect user-selected ATS boards, then fetch descriptions for title matches.

Board inventory, search queries and optional title pattern are explicit inputs.
No employer list, target role or location preference is bundled.

Usage: python fetch_all.py --boards local-config/boards.json --query "research"
Output: local-data/cache_all/_matches.json.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from fetch_jobs import strip_html

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "local-data", "cache_all")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

TITLE_RE = re.compile(r".*")
QUERIES = []


def req(url, data=None, timeout=25):
    h = {"User-Agent": UA, "Accept": "application/json"}
    if data is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    r = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


# ----------------------------------------------------------------- per-ATS
def wd_parts(handle):
    ten, wd, site = handle.split("|")
    return ten, wd, site


def list_workday(h):
    ten, wd, site = wd_parts(h)
    base = "https://%s.%s.myworkdayjobs.com/wday/cxs/%s/%s" % (ten, wd, ten, site)
    seen, out = set(), []
    for q in QUERIES:
        off = 0
        while off < 200:                      # server-side filtered; stays small
            try:
                d = req(base + "/jobs", {"appliedFacets": {}, "limit": 20,
                                         "offset": off, "searchText": q})
            except Exception:
                break
            posts = d.get("jobPostings") or []
            for p in posts:
                path = p.get("externalPath") or ""
                if path in seen:
                    continue
                seen.add(path)
                out.append({"title": p.get("title", ""),
                            "location": p.get("locationsText", ""),
                            "path": path, "url": "https://%s.%s.myworkdayjobs.com/%s%s"
                            % (ten, wd, site, path)})
            if len(posts) < 20:
                break
            off += 20
    return out


def desc_workday(h, job):
    ten, wd, site = wd_parts(h)
    try:
        d = req("https://%s.%s.myworkdayjobs.com/wday/cxs/%s/%s%s"
                % (ten, wd, ten, site, job["path"]))
    except Exception:
        return ""
    info = d.get("jobPostingInfo") or {}
    return strip_html(info.get("jobDescription", ""))


def list_smartrecruiters(h):
    out = []
    for q in QUERIES:
        try:
            d = req("https://api.smartrecruiters.com/v1/companies/%s/postings?limit=100&q=%s"
                    % (h, urllib.parse.quote(q)))
        except Exception:
            continue
        for p in d.get("content", []):
            loc = p.get("location") or {}
            out.append({"title": p.get("name", ""), "id": p.get("id", ""),
                        "location": ", ".join(x for x in [loc.get("city"), loc.get("region"),
                                                          loc.get("country")] if x),
                        "url": "https://jobs.smartrecruiters.com/%s/%s" % (h, p.get("id", ""))})
    return out


def desc_smartrecruiters(h, job):
    try:
        d = req("https://api.smartrecruiters.com/v1/companies/%s/postings/%s" % (h, job["id"]))
    except Exception:
        return ""
    secs = ((d.get("jobAd") or {}).get("sections") or {})
    return strip_html(" ".join((secs.get(k) or {}).get("text", "")
                               for k in ("jobDescription", "qualifications", "companyDescription")))


def list_simple(ats, h):
    """Boards small enough to pull whole and filter locally."""
    try:
        if ats == "greenhouse":
            d = req("https://boards-api.greenhouse.io/v1/boards/%s/jobs?content=true" % h)
            return [{"title": j.get("title", ""), "location": (j.get("location") or {}).get("name", ""),
                     "url": j.get("absolute_url", ""), "desc": strip_html(j.get("content", ""))}
                    for j in d.get("jobs", [])]
        if ats == "lever":
            d = req("https://api.lever.co/v0/postings/%s?mode=json" % h)
            return [{"title": j.get("text", ""),
                     "location": (j.get("categories") or {}).get("location", "") or "",
                     "url": j.get("hostedUrl", ""),
                     "desc": strip_html(j.get("descriptionPlain") or j.get("description", ""))}
                    for j in d]
        if ats == "ashby":
            d = req("https://api.ashbyhq.com/posting-api/job-board/%s?includeCompensation=true" % h)
            return [{"title": j.get("title", ""), "location": j.get("location", "") or "",
                     "url": j.get("jobUrl", "") or j.get("applyUrl", ""),
                     "desc": strip_html(j.get("descriptionHtml") or j.get("descriptionPlain", ""))}
                    for j in d.get("jobs", [])]
        if ats == "workable":
            d = req("https://apply.workable.com/api/v1/widget/accounts/%s" % h)
            return [{"title": j.get("title", ""),
                     "location": ", ".join(x for x in [j.get("city"), j.get("country")] if x),
                     "url": j.get("url", ""), "desc": strip_html(j.get("description", ""))}
                    for j in (d.get("jobs") or [])]
        if ats == "recruitee":
            d = req("https://%s.recruitee.com/api/offers/" % h)
            return [{"title": j.get("title", ""), "location": j.get("location", "") or "",
                     "url": j.get("careers_url", ""), "desc": strip_html(j.get("description", ""))}
                    for j in (d.get("offers") or [])]
    except Exception:
        return []
    return []


# --------------------------------------------------------------------- run
def handle_board(b):
    ats, h = b["ats"], b["handle"]
    try:
        if ats == "workday":
            jobs = [j for j in list_workday(h) if TITLE_RE.search(j["title"])]
            for j in jobs:
                j["desc"] = desc_workday(h, j)
                time.sleep(0.15)
        elif ats == "smartrecruiters":
            jobs = [j for j in list_smartrecruiters(h) if TITLE_RE.search(j["title"])]
            for j in jobs:
                j["desc"] = desc_smartrecruiters(h, j)
                time.sleep(0.15)
        else:
            jobs = [j for j in list_simple(ats, h) if TITLE_RE.search(j["title"])]
    except Exception:
        return b, []
    for j in jobs:
        j["company"] = b["company"]
        j["ats"] = ats
        j["handle"] = h
    return b, jobs


def main():
    global CACHE, TITLE_RE, QUERIES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boards", required=True, help="JSON list: company, ats, handle")
    parser.add_argument("--query", nargs="+", required=True, help="Explicit source search terms")
    parser.add_argument("--title-pattern", help="Optional case-insensitive regex; absent accepts every returned title")
    parser.add_argument("--output-dir", default=CACHE)
    parser.add_argument("--limit", type=int, help="Maximum selected boards")
    args = parser.parse_args()
    CACHE = args.output_dir
    TITLE_RE = re.compile(args.title_pattern or r".*", re.I)
    QUERIES = [q.strip() for q in args.query if q.strip()]
    if not QUERIES:
        parser.error("Supply at least one nonempty query")
    with open(args.boards, encoding="utf-8-sig") as stream:
        boards = json.load(stream)
    supported = {"workday", "smartrecruiters", "greenhouse", "lever", "ashby", "workable", "recruitee"}
    if not isinstance(boards, list):
        parser.error("Board inventory must be a list")
    for board in boards:
        if (not isinstance(board, dict) or not all(isinstance(board.get(k), str) and board[k]
                                                for k in ("company", "ats", "handle"))
                or board["ats"] not in supported):
            parser.error("Each board requires company, supported ats and handle")
        handle = board["handle"]
        if board["ats"] == "workday":
            parts = handle.split("|")
            if len(parts) != 3 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
                parser.error("Workday handle must be tenant|host|site")
        elif not re.fullmatch(r"[A-Za-z0-9_.-]+", handle):
            parser.error("Board handles must be URL-safe tokens")
    out_name = "_matches.json"
    seen, uniq = set(), []
    for b in boards:
        k = (b["ats"], b["handle"])
        if k not in seen:
            seen.add(k)
            uniq.append(b)
    if args.limit is not None:
        if args.limit < 0:
            parser.error("--limit cannot be negative")
        uniq = uniq[:args.limit]

    os.makedirs(CACHE, exist_ok=True)
    print("fetching %d boards\n" % len(uniq))
    allm, done = [], 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for b, jobs in pool.map(handle_board, uniq):
            done += 1
            if jobs:
                allm += jobs
                print("  %-34s %-12s %3d matching roles" % (b["company"][:33], b["ats"], len(jobs)))
            if done % 50 == 0:
                print("  ... %d/%d boards, %d matches so far" % (done, len(uniq), len(allm)))
    json.dump(allm, open(os.path.join(CACHE, out_name), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("\n%d title-matched postings from %d boards -> cache_all/%s"
          % (len(allm), len(uniq), out_name))


if __name__ == "__main__":
    main()
