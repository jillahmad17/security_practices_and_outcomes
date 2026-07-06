"""
create_cloc_dataset.py

Reads all cloc YAML output files produced by ClocAnalyzer and joins them
with the original CSV to produce a flat dataset.

Each output row corresponds to one (package, tag, commit) entry and contains
the four SUM fields from cloc: nFiles, blank, comment, code.
Any SUM field whose raw value is not a valid integer is written as empty.

Also produces a *missing* dataset: every CSV row for which no YAML file was
found on disk, together with a `missing_reason` column that explains why
(yaml_not_found | parse_error | no_csv_match | invalid_github_url).

Key design decisions
--------------------
* Path reconstruction is driven by the original CSV rather than inverting the
  `repo_name.replace("/", "__")` transform.  That transform is non-injective:
  a repo whose name natively contains "__" would be indistinguishable from
  the "/" separator after substitution.  By re-deriving the expected path
  from the CSV we avoid this collision entirely.

* No external YAML library is required.  The parser targets only the SUM
  block of cloc's actual output format, which uses single-quoted language
  keys and a flat header block with scalar values:

      ---
      # github.com/AlDanial/cloc
      header :
        cloc_url : ...
        n_files  : 78          <- scalars, not sub-dicts
        ...
      'Python' :
        nFiles: 48
        ...
      SUM:
        blank: 1746
        comment: 936
        code: 11738
        nFiles: 78
"""

import csv
import re
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SUM-only YAML parser
# ---------------------------------------------------------------------------

def _safe_int(raw: str) -> Optional[int]:
    """Return int(raw) or None if raw is not a valid integer."""
    try:
        return int(raw.strip())
    except (ValueError, TypeError):
        return None


def parse_cloc_yaml_sum(path: Path) -> Optional[Dict[str, Optional[int]]]:
    """
    Extract only the SUM block from a cloc --yaml output file.

    Returns a dict with keys nFiles, blank, comment, code.
    Values are int, or None when the raw value is not a valid number.
    Returns None if the SUM block is not found or the file cannot be read.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"Cannot read {path}: {e}")
        return None

    # A top-level SUM key looks like:  SUM:  or  SUM :  or  'SUM' :
    SUM_KEY = re.compile(r"^'?SUM'?\s*:\s*$")
    FIELD   = re.compile(r"^\s+(nFiles|blank|comment|code)\s*:\s*(.+)$")
    TOP_KEY = re.compile(r"^\S")  # non-indented line signals a new block

    in_sum = False
    result: Dict[str, Optional[int]] = {}

    for line in text.splitlines():
        stripped = line.rstrip()

        if SUM_KEY.match(stripped):
            in_sum = True
            continue

        if in_sum:
            # A new top-level key ends the SUM block
            if TOP_KEY.match(stripped) and stripped and not stripped.startswith("#"):
                break
            m = FIELD.match(stripped)
            if m:
                field, raw = m.group(1), m.group(2).strip()
                result[field] = _safe_int(raw)

    if not result:
        logger.warning(f"No SUM block found in {path}")
        return None

    # Guarantee all four keys are present (None when missing or non-numeric)
    for field in ("nFiles", "blank", "comment", "code"):
        result.setdefault(field, None)

    return result


# ---------------------------------------------------------------------------
# Path index: CSV-driven, no path inversion
# ---------------------------------------------------------------------------

def build_path_index(
    cloc_results_dir: Path,
    csv_rows: List[Dict],
) -> Tuple[Dict[Path, Tuple[str, str]], List[Dict]]:
    """
    Build a mapping  yaml_path -> (github_url, commit_sha)  using the CSV
    as the authoritative source.

    Also returns a list of missing-row dicts for entries whose YAML was not
    found on disk (reason: yaml_not_found or invalid_github_url).

    For each CSV row we reconstruct the expected YAML path using the same
    naming logic as ClocAnalyzer:
        safe_dir  = "{owner}__{repo_name_only}"
        yaml_file = "{commit_sha}.yaml"
    """
    mapping: Dict[Path, Tuple[str, str]] = {}
    missing_rows: List[Dict] = []

    for row in csv_rows:
        github_url = row["github_repo"].rstrip("/").replace(".git", "")
        parts = github_url.split("github.com/")
        if len(parts) < 2:
            logger.warning(f"Unrecognised GitHub URL, skipping: {row['github_repo']}")
            missing_rows.append({**row, "missing_reason": "invalid_github_url"})
            continue

        repo_name  = parts[-1]   # e.g. "openvoiceos/ovos-phal-plugin-wallpaper-manager"
        commit_sha = row["tag_commit_sha"]

        owner_name, _, repo_name_only = repo_name.partition("/")
        safe_dir  = f"{owner_name}__{repo_name_only}"
        yaml_path = cloc_results_dir / safe_dir / f"{commit_sha}.yaml"

        if yaml_path.exists():
            mapping[yaml_path] = (github_url, commit_sha)
        else:
            logger.debug(f"No YAML for {repo_name} @ {commit_sha[:8]}: expected {yaml_path}")
            missing_rows.append({**row, "missing_reason": "yaml_not_found"})

    found = len(mapping)
    missing = len(missing_rows)
    logger.info(f"Path index: {found} found, {missing} not on disk")
    return mapping, missing_rows


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------

def build_dataset(
    csv_file: str,
    cloc_results_dir: str = "cloc_results",
    output_csv: str = "cloc_dataset.csv",
    output_parquet: Optional[str] = "cloc_dataset.parquet",
    missing_csv: str = "cloc_missing.csv",
    missing_parquet: Optional[str] = "cloc_missing.parquet",
) -> None:
    """
    Parameters
    ----------
    csv_file          : original input CSV passed to ClocAnalyzer
    cloc_results_dir  : directory where ClocAnalyzer wrote YAML files
    output_csv        : output CSV path for successfully parsed rows
    output_parquet    : output Parquet path for successfully parsed rows (None to skip)
    missing_csv       : output CSV path for rows with no matching/parseable YAML
    missing_parquet   : output Parquet path for missing rows (None to skip)
    """
    csv_path    = Path(csv_file)
    results_dir = Path(cloc_results_dir)

    if not csv_path.exists():
        logger.error(f"CSV not found: {csv_path}")
        sys.exit(1)
    if not results_dir.exists():
        logger.error(f"cloc results directory not found: {results_dir}")
        sys.exit(1)

    # 1. Load CSV
    with open(csv_path, newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    logger.info(f"Loaded {len(csv_rows)} rows from {csv_path}")

    # Index by (normalised_url, commit_sha) for O(1) lookup
    csv_index: Dict[Tuple[str, str], Dict] = {}
    for row in csv_rows:
        url_norm = row["github_repo"].rstrip("/").replace(".git", "")
        csv_index[(url_norm, row["tag_commit_sha"])] = row

    # 2. Build path index (also collects yaml_not_found / invalid_github_url missing rows)
    path_index, missing_rows = build_path_index(results_dir, csv_rows)

    # 3. Parse YAML files and join with CSV metadata
    output_rows: List[Dict] = []
    parse_errors = 0

    for yaml_path, (github_url, commit_sha) in path_index.items():
        url_norm = github_url.rstrip("/").replace(".git", "")
        csv_row  = csv_index.get((url_norm, commit_sha))
        if csv_row is None:
            logger.warning(f"No CSV row matched for {github_url} @ {commit_sha[:8]}")
            # Synthesise a minimal missing row since we have no CSV data to copy
            missing_rows.append({
                "github_repo":    github_url,
                "package_name":   "",
                "tag_name":       "",
                "tag_commit_sha": commit_sha,
                "published_at":   "",
                "status":         "",
                "System":         "",
                "missing_reason": "no_csv_match",
            })
            continue

        sum_data = parse_cloc_yaml_sum(yaml_path)
        if sum_data is None:
            parse_errors += 1
            sum_data = {"nFiles": None, "blank": None, "comment": None, "code": None}

        output_rows.append({
            "github_repo":    csv_row["github_repo"],
            "package_name":   csv_row["package_name"],
            "tag_name":       csv_row["tag_name"],
            "tag_commit_sha": commit_sha,
            "published_at":   csv_row.get("published_at", ""),
            "status":         csv_row.get("status", ""),
            "System":         csv_row.get("System", ""),
            "sum_nFiles":     sum_data["nFiles"],
            "sum_blank":      sum_data["blank"],
            "sum_comment":    sum_data["comment"],
            "sum_code":       sum_data["code"],   # None if parse failed
        })

    logger.info(
        f"Parsed {len(output_rows) + parse_errors} YAML files — "
        f"{len(output_rows)} OK, {parse_errors} parse errors"
    )
    logger.info(f"{parse_errors} rows had parse errors — included in main dataset with null cloc fields")
    logger.info(
        f"Missing rows total: {len(missing_rows)} "
        f"({sum(1 for r in missing_rows if r['missing_reason'] == 'yaml_not_found')} yaml_not_found, "
        f"{sum(1 for r in missing_rows if r['missing_reason'] == 'no_csv_match')} no_csv_match, "
        f"{sum(1 for r in missing_rows if r['missing_reason'] == 'invalid_github_url')} invalid_github_url)"
    )

    if not output_rows:
        logger.error("No output rows — nothing to write.")
        sys.exit(1)

    # 4. Write main CSV
    fieldnames = list(output_rows[0].keys())
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)
    logger.info(f"Wrote {len(output_rows)} rows to {output_csv}")

    # 5. Write missing CSV
    if missing_rows:
        # Collect all keys that appear across missing rows, ensure missing_reason is last
        missing_keys: List[str] = []
        seen_keys: set = set()
        for row in missing_rows:
            for k in row:
                if k not in seen_keys and k != "missing_reason":
                    missing_keys.append(k)
                    seen_keys.add(k)
        missing_keys.append("missing_reason")

        with open(missing_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=missing_keys, extrasaction="ignore", restval=""
            )
            writer.writeheader()
            writer.writerows(missing_rows)
        logger.info(f"Wrote {len(missing_rows)} missing rows to {missing_csv}")
    else:
        logger.info("No missing rows — skipping missing CSV")

    # 6. Optionally write Parquet files
    try:
        import pandas as pd  # type: ignore

        # Main dataset
        df = pd.DataFrame(output_rows)
        for col in ("sum_nFiles", "sum_blank", "sum_comment", "sum_code"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        if output_parquet:
            df.to_parquet(output_parquet, index=False)
            logger.info(f"Wrote Parquet to {output_parquet}  shape={df.shape}")

        # Missing dataset
        if missing_rows and missing_parquet:
            df_missing = pd.DataFrame(missing_rows)
            df_missing.to_parquet(missing_parquet, index=False)
            logger.info(f"Wrote missing Parquet to {missing_parquet}  shape={df_missing.shape}")

    except ImportError:
        logger.warning("pandas/pyarrow not available — skipping Parquet output")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build a flat dataset from ClocAnalyzer YAML outputs."
    )
    parser.add_argument(
        "--csv", default="dataset.csv",
        help="Original input CSV (default: dataset.csv)",
    )
    parser.add_argument(
        "--results-dir", default="cloc_results",
        help="Directory containing cloc YAML outputs (default: cloc_results)",
    )
    parser.add_argument(
        "--output-csv", default="cloc_dataset.csv",
        help="Output CSV path (default: cloc_dataset.csv)",
    )
    parser.add_argument(
        "--output-parquet", default="cloc_dataset.parquet",
        help="Output Parquet path (default: cloc_dataset.parquet); pass empty string to skip",
    )
    parser.add_argument(
        "--missing-csv", default="cloc_missing.csv",
        help="Output CSV path for missing entries (default: cloc_missing.csv)",
    )
    parser.add_argument(
        "--missing-parquet", default="cloc_missing.parquet",
        help="Output Parquet path for missing entries (default: cloc_missing.parquet); pass empty string to skip",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable DEBUG logging (shows every missing YAML path)",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    build_dataset(
        csv_file=args.csv,
        cloc_results_dir=args.results_dir,
        output_csv=args.output_csv,
        output_parquet=args.output_parquet or None,
        missing_csv=args.missing_csv,
        missing_parquet=args.missing_parquet or None,
    )


if __name__ == "__main__":
    main()