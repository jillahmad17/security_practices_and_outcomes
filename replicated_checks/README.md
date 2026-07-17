# Replicated Scorecard Checks


These are the scorecard checks that have been reconstructed to return historical data. The contributors, dependency-update-tool, and maintained check use a modified version of OpenSSF Scorecard located at ./scorecard and are documented here. The fuzzing check and documentation is located at ./fuzzing_check

# Contributors, Dependency-Update-Tool, and Maintained

## Requirements

* Go version 1.23+

* A valid Github personal access token


## Usage

On Linux and Mac:

```bash
export GITHUB_AUTH_TOKEN=<YOUR ACCESS TOKEN>
```

On Windows:

```bash
set GITHUB_AUTH_TOKEN=<YOUR ACCESS TOKEN>
```

# Contributors

This is a  version of OpenSSF Scorecard that contains modifications to the contributors check. This check determines if there have been contributions from multiple organizations within the 30 most recent commits of a given moment in time specified by a commit hash.

./scorecard contains the modified version of OpenSSF Scorecard. ./custom-go-github contains a modified version of the github.com/google/go-github/v53 go module used by Scorecard.




in the ./scorecard folder

```bash
go run main.go --repo="<YOUR_REPO>" --commit="<COMMIT_HASH>" --checks="Contributors"
```

# Dependency-Update-Tool

This is a  version of OpenSSF Scorecard that contains modifications to the dependency update tool check. This check determines if a project used [Dependabot](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference) or [Renovate Bot](https://docs.renovatebot.com/configuration-options/) at a particular moment in the project's history. 





in the ./scorecard folder

```bash
go run main.go --repo="<YOUR_REPO>" --commit="<COMMIT_HASH>" --commit-date="<COMMIT_DATE>" --checks="Dependency-Update-Tool"
```

Note that this is the only check that requires the commit-date flag


# Maintained

This is a  version of OpenSSF Scorecard that contains modifications to the Maintained check. This check determines if a project was actively maintained at a given point of time. It checks for commits in the last 90 days from the point of time and the most recent activity on issues.

This check depends on a large database of [IssuesEvent]s(https://docs.github.com/en/rest/using-the-rest-api/github-event-types?apiVersion=2026-03-10#issuesevent)s and [IssueCommentEvent](https://docs.github.com/en/rest/using-the-rest-api/github-event-types?apiVersion=2026-03-10#issuecommentevent)s taken from [Github Archive](https://www.gharchive.org/). This database was too large to include in this repository so a sample of values for an example repository from our dataset (github.com/0x-jerry/utils) is included in ./issue-events-partitioned-name. To use this tool to calculate historical scorecard scores, you must have IssuesEvents and IssueCommentEvents partitioned by repository name, where there is one folder of parquet files per repository.

in the ./scorecard folder

```bash
go run main.go --repo="<YOUR_REPO>" --commit="<COMMIT_HASH>" --checks="Maintained"
```
