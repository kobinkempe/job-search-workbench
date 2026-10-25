# Local pipeline and configuration

The public browser demo is in `demo/`; `python serve.py` serves only those files on loopback. It does not call a model, scrape sites, save imports or provide a persistence API. An external AI agent does the web research described by the downloadable brief. Browser imports remain in memory and always require verification.

The optional Python pipeline is a separate local workflow. It uses explicit operator inputs; no employer inventory, role target, applicant background, location preference, salary baseline or experience cutoff is built in. Empty criteria include every posting at score zero. It uses only the Python standard library (Python 3.10+).

## 1. Supply inputs

Keep private configuration in `local-config/` and collected data in `local-data/`; both are ignored by Git. Copy the empty inventories or neutral criteria from `examples/` to start.

A seed inventory for `fetch_jobs.py` is a JSON object of category names to arrays of ATS tokens. `examples/seeds.example.json` is `{}`, so running it makes no requests. A real token is supplied by the operator after checking the employer's public career page. Tokens are not proof an employer or board exists.

A board inventory for `fetch_all.py` is a JSON array. Each item has `company`, `ats` and `handle` strings. Supported adapters are `greenhouse`, `lever`, `ashby`, `workday`, `smartrecruiters`, `workable` and `recruitee`. Workday handles use `tenant|host|site`; the other adapters take an account token. `examples/boards.example.json` is `[]` and contains no real employers.

Use only sources you are permitted to access. Adapter endpoints and response shapes may change; an empty result can mean a failed request, not that a company has no openings. No live endpoint validation was performed for the portfolio version.

```sh
python fetch_jobs.py --seeds local-config/seeds.json
python fetch_all.py --boards local-config/boards.json --query "research" --title-pattern "analyst|researcher" --limit 5
```

The second example illustrates arguments, not a suggested personal search. The query is used server-side where supported (Workday and SmartRecruiters); other adapters may retrieve a whole selected board before applying the explicit title regex. No title regex means all returned titles. Source pagination limits and broad queries can produce incomplete coverage; inspect the original board.

Both collectors write local normalized JSON, with title, location, URL and description. `fetch_jobs.py` writes `local-data/cache/raw_<token>.json`; `fetch_all.py` writes `local-data/cache_all/_matches.json`. The offline tools also accept the browser's `{"jobs": [...]}` JSON shape, including `source_url` instead of `url`.

## 2. Define explicit criteria, if wanted

`examples/criteria.example.json` lists the full neutral configuration. Omit `--criteria` to use those same empty defaults.

| Field | Meaning |
| --- | --- |
| `version` | Schema version, currently `1`. |
| `title_include`, `location_include` | Case-insensitive regexes. An empty array accepts every value; a nonempty array requires at least one hit. |
| `title_exclude`, `location_exclude` | Case-insensitive regexes that exclude a row from passing the configured rules. Defaults are empty. |
| `work_modes` | Allowed heuristic values: `remote`, `hybrid`, `onsite`, `unclear`. Empty accepts all. |
| `min_required_years`, `max_required_years` | Optional bounds on the highest explicit experience minimum found in the description. Default `null`. This can refer to a particular skill, not total experience. |
| `include_unknown_experience` | Retain rows when no explicit numeric requirement is found. Default `true`. |
| `weighted_terms` | Objects with `label`, `pattern` and numeric `weight`. Each matching regex adds its configured weight once. Empty means score zero. |

For example, a person researching analyst work could explicitly add `{"label":"analysis","pattern":"analysis|analytics","weight":2}` to `weighted_terms`. This is an illustrative search signal, not evidence of applicant fit. No inferred background or preferred industry changes the score.

```sh
python filter_jobs.py --postings local-data/cache_all/_matches.json --criteria local-config/criteria.json
```

The CSV retains every row, including those that fail explicit rules. `passes_criteria` and `criteria_reasons` explain the result. A regex match does not verify a requirement or a person's eligibility. Dollar-range extraction retains stated amounts without currency conversion, period conversion or cost-of-living adjustment. Confirm the currency and annual/hourly basis at the source.

## 3. Join an intake list to source descriptions

An optional CSV or TSV intake has `company`, `title`, `location` and `url`/`source_url` columns. Pass exact JSON inputs instead of relying on hidden cache directories:

```sh
python build_final.py --intake local-data/intake.tsv --postings local-data/cache_all/_matches.json --criteria local-config/criteria.json
```

`--intake` and `--criteria` are optional. Without an intake, every collected row is included. Output defaults to `local-data/combined.csv`.

The join keeps all intake rows, then appends collected rows not used by a match. Duplicate observations of the same URL prefer a nonempty description and location. Distinct URLs stay separate. An exact URL match takes priority. Company/title equality or fuzzy title overlap produces an explicitly labeled **candidate**, and ambiguous candidates remain unmatched rather than arbitrarily choosing a description. All rows have `needs_review`, including exact URL matches: a source can change or close.

## 4. Export for browser review

```sh
python build_viewer_data.py --combined local-data/combined.csv --output local-data/research-import.json
```

Import that file using the browser's **Import its JSON results** control. Exported records use the current browser schema: `title`, `company`, `role_family`, `industry`, `source_url`, `checked_at`, `source_excerpt`, `description` and `open_questions`. All are unverified. Candidate joins add a question asking the reader to confirm the description belongs to the intake posting. The exporter rejects collections outside the browser's 1–500 record / 2 MB bounds; split large collections before import. It never overwrites the fictional demo or viewer files.

No source excerpt or check date is fabricated when an adapter does not supply one. A person or research agent must add evidence from the original page. Scoring metadata and local-only fields remain in the CSV, rather than becoming claims in the public browser collection.

## Offline verification

```sh
python -m unittest discover -s tests -v
```

The tests exercise neutral defaults, custom inclusion/exclusion and weights, validation, salary/experience evidence, source deduplication and match confidence, export compatibility, adapter normalization and explicit-input requirements. They use only invented records and mocked responses; no job board is contacted.
