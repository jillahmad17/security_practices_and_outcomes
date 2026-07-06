import os
import pandas as pd
import json

# --- Load dataframe ---
df = pd.read_csv("dataset.csv")

# Normalize repo to owner__repo
def repo_to_dir(url):
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("github.com/")[-1]
    owner, repo = parts.split("/")
    return f"{owner}__{repo}"

df["repo_dir"] = df["github_repo"].apply(repo_to_dir)

# Path to cloc results
CLOC_DIR = "cloc_results"

full_failures_rows = []
partial_failures_rows = []

# Group by repo
repo_groups = df.groupby("repo_dir")

for repo_dir, group in repo_groups:
    repo_path = os.path.join(CLOC_DIR, repo_dir)
    expected_commits = set(group["tag_commit_sha"])

    if not os.path.isdir(repo_path):
        # Full failure: repo missing → all rows go here
        full_failures_rows.append(group)
        continue

    actual_commits = set(f.replace(".yaml", "") for f in os.listdir(repo_path) if f.endswith(".yaml"))
    missing_commits = expected_commits - actual_commits

    if missing_commits:
        # Partial failure: some commits missing
        partial_failures_rows.append(group[group["tag_commit_sha"].isin(missing_commits)])

# Concatenate all groups
if full_failures_rows:
    full_failures_df = pd.concat(full_failures_rows)
    full_failures_df.to_csv("full_failures.csv", index=False)
else:
    pd.DataFrame().to_csv("full_failures.csv", index=False)

if partial_failures_rows:
    partial_failures_df = pd.concat(partial_failures_rows)
    partial_failures_df.to_csv("partial_failures.csv", index=False)
else:
    pd.DataFrame().to_csv("partial_failures.csv", index=False)

# Summary
summary = {
    "total_repos": len(repo_groups),
    "full_failures": len(full_failures_rows),
    "partial_failures": len(partial_failures_rows)
}

print("Done. Summary:", summary)