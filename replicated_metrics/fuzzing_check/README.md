# fuzzing_check

Pipeline for checking whether each package/release entry in an input dataset is fuzz-tested, using three independent signals: presence in [OSS-Fuzz](https://github.com/google/oss-fuzz), use of [ClusterFuzzLite](https://google.github.io/clusterfuzzlite/), and language-specific fuzzing harnesses (e.g. Go's built-in fuzzing, libFuzzer, Atheris, Jazzer, property-based testing frameworks).

This is provided for reproducibility purposes — the scripts document the exact process used to generate the data, not a maintained tool.

## Requirements

- Python 3.9+, packages in `requirements.txt` (`pip install -r requirements.txt`)
- `git` available on `PATH`
- A GitHub personal access token (for the language-detection API call), or several tokens for rotation on large datasets

## Input

A CSV with, at minimum, the following columns:

- `github_repo` — GitHub URL of the source repo
- `tag_commit_sha` — commit the release tag points to
- `published_at` — ISO timestamp of the release (used to pick the closest-in-time OSS-Fuzz commit)
- `project_name` — used for progress/log messages

## Pipeline

Each row is checked independently by `FuzzingCheckOrchestrator` (`processor.py`):

1. **OSS-Fuzz check** (`ossfuzz_checker.py`) — the local `oss-fuzz` repo (`OSSFuzzRepoManager`) is checked out to the commit closest to (but not after) the row's `published_at` date, then `projects/*/project.yaml` files are scanned for a URL matching `github_repo`.
2. **Repo clone/checkout** (`git_manager.py`) — clones `github_repo` (or reuses it if already checked out) and checks out `tag_commit_sha`. Only one repo is kept on disk at a time; switching to a different repo deletes the previous one.
3. **ClusterFuzzLite check** (`cflite_checker.py`) — looks for a `.clusterfuzzlite/Dockerfile` with real commands, or a GitHub Actions workflow referencing `clusterfuzzlite`.
4. **Language-specific fuzzing check** (`language_checker.py`) — queries the GitHub languages API for the repo's prominent languages, then greps the checked-out tree for language-specific fuzzing/property-testing patterns (see `LANGUAGE_SPECS` in `language_checker.py` for the full list of languages and patterns).

A row's `fuzzing_score` is `10` if any of the three checks found evidence of fuzzing, otherwise `0`.

State is checkpointed to disk so the run can be interrupted (`Ctrl+C`) and resumed:
- `<output_csv>` — rows processed so far are already written back with results
- `fuzzing_state.json` — index of the last row processed
- `fuzzing_failures.log` — one line per error (`Row X | repo @ sha | error`)

## Usage

```bash
python main.py dataset.csv results.csv
```

Options:

- `--github-token TOKEN` — GitHub token for language detection (defaults to `$GITHUB_TOKEN`)
- `--use-token-rotation` — rotate across `GITHUB_TOKEN_1`, `GITHUB_TOKEN_2`, `GITHUB_TOKEN_3` (set these as environment variables first)
- `--no-resume` — ignore any existing output/state and start fresh; also sorts the dataset by `published_at` first so repeated OSS-Fuzz checkouts are minimized
- `--repos-dir DIR` — where package repos are cloned (default `./repos`)
- `--ossfuzz-dir DIR` — where the OSS-Fuzz repo is cloned (default `./oss-fuzz-repo`)
- `--save-frequency N` — write progress to disk every N rows (default `10`)

## Output columns

- `ossfuzz_check`, `ossfuzz_project`, `ossfuzz_error`
- `cflite_check`, `cflite_error`
- `lang_fuzzing` (JSON object of `{language: bool}`), `lang_error`
- `fuzzing_score` — `10` or `0`, per the rule above

## extract_failures.py

A standalone helper for re-driving failed rows: parses `fuzzing_failures.log` for unique repo URLs, then pulls every matching row out of the original dataset into a new CSV for re-processing.

```bash
python extract_failures.py fuzzing_failures.log dataset.csv failed_repos.csv
```

## Notes

- Only one package repo is kept checked out at a time — the pipeline is not parallelized across repos.
- The OSS-Fuzz repo is re-checked-out per row only when the release date differs from the previous row's, so sorting the input by `published_at` (done automatically with `--no-resume`) avoids redundant checkouts.
- Failed rows are logged but do not stop the run.
