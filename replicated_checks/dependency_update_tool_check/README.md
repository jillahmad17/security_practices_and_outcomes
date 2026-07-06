# dependency-update-tool-check

This is a  version of OpenSSF Scorecard that contains modifications to the dependency update tool check. This check determines if a project used [Dependabot](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference) or [Renovate Bot](https://docs.renovatebot.com/configuration-options/) at a particular moment in the project's history. 


## Requirements

* Go version 1.23+

* A valid Github personal access token

## Input

%Y-%m-%dT%H:%M:%SZ


## Usage

On Linux and Mac:

```bash
export GITHUB_AUTH_TOKEN=<YOUR ACCESS TOKEN>

```

On Windows:

```bash
set GITHUB_AUTH_TOKEN=<YOUR ACCESS TOKEN>

```

in the ./scorecard folder

```bash
go run main.go --repo="<YOUR_REPO>" --commit="<COMMIT_HASH>" --commit-date="<COMMIT_DATE>" --checks="Dependency-Update-Tool"
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