# lines_of_code

Pipeline for measuring lines-of-code metrics (via [`cloc`](https://github.com/AlDanial/cloc)) for every package/release entry in `dataset.csv`, at the exact commit each release was tagged at.

This is provided for reproducibility purposes — the scripts document the exact process used to generate the data, not a maintained tool.

## Requirements

- Python 3.9+, packages in `requirements.txt` (`pip install -r requirements.txt`)
- `git` and [`cloc`](https://github.com/AlDanial/cloc) available on `PATH`
- `pandas`/`pyarrow` optional but needed for Parquet output in `create_cloc_dataset.py`

## Input

`dataset.csv` — one row per (package, release tag), with columns:

- `github_repo` — GitHub URL of the source repo
- `tag_name`, `release_tag_name`, `published_at`, `status`
- `tag_commit_sha` — commit the release tag points to
- `project_name`, `package_name`, `System` (e.g. `PYPI`)

## Pipeline

1. **`lines_of_code.py`** — `ClocAnalyzer` reads a CSV of entries (default `partial_failures.csv`), and for each row:
   - clones `github_repo` into `repos_cache/` (skipped if already cloned)
   - checks out `tag_commit_sha`
   - runs `cloc --yaml` against the checked-out tree, writing output to `cloc_results/{owner}__{repo}/{commit_sha}.yaml`

   State is checkpointed to disk so the run can be interrupted and resumed:
   - `cloc_progress.txt` — entries already processed successfully
   - `cloc_failures.txt` — pipe-delimited failure log (`github_url|commit_sha|package_name|tag_name|reason`); repos/packages that failed once (clone failure, etc.) are skipped on subsequent entries
   - `cloc_analysis.log` — full run log

   Cloned repos are cached in `repos_cache/` and are **not** deleted between entries (cleanup calls are present but commented out), since many rows share the same repo across releases.

2. **`generate_failures.py`** — diffs `dataset.csv` against what's actually present in `cloc_results/` to find gaps, producing:
   - `full_failures.csv` — rows for repos with no output directory at all
   - `partial_failures.csv` — rows for repos that exist but are missing specific commits (this is the file `lines_of_code.py` re-runs against to fill gaps)

3. **`create_cloc_dataset.py`** — joins the `cloc_results/*.yaml` outputs back onto `dataset.csv` to produce a flat dataset. Path lookup is driven by the CSV (owner/repo + commit sha) rather than by inverting directory names, since the `/` → `__` substitution used for directory names is not reversible in general.

   ```
   python create_cloc_dataset.py \
     --csv dataset.csv \
     --results-dir cloc_results \
     --output-csv cloc_dataset.csv \
     --output-parquet cloc_dataset.parquet \
     --missing-csv cloc_missing.csv \
     --missing-parquet cloc_missing.parquet
   ```

   Outputs:
   - main dataset: one row per matched entry with `sum_nFiles`, `sum_blank`, `sum_comment`, `sum_code` (the `cloc` SUM block), alongside the original CSV columns
   - missing dataset: rows that couldn't be resolved, tagged with `missing_reason` (`yaml_not_found`, `parse_error`, `no_csv_match`, `invalid_github_url`)

## Typical run order

```
python lines_of_code.py          # crawl dataset.csv (or partial_failures.csv), populate cloc_results/
python generate_failures.py      # find gaps -> full_failures.csv / partial_failures.csv
python lines_of_code.py          # re-run against partial_failures.csv to fill gaps (repeat as needed)
python create_cloc_dataset.py    # flatten cloc_results/ into cloc_dataset.csv/.parquet
```
