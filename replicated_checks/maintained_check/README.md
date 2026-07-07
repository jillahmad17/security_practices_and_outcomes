# maintained_check

This is a  version of OpenSSF Scorecard that contains modifications to the Maintained check. This check determines if a project was actively maintained at a given point of time. It checks for commits in the last 90 days from the point of time and the most recent activity on issues.

This check depends on a large database of [IssuesEvent]s(https://docs.github.com/en/rest/using-the-rest-api/github-event-types?apiVersion=2026-03-10#issuesevent)s and [IssueCommentEvent](https://docs.github.com/en/rest/using-the-rest-api/github-event-types?apiVersion=2026-03-10#issuecommentevent)s taken from [Github Archive](https://www.gharchive.org/). This database was too large to include in this repository so a sample of values for an example repository (github.com/0x-jerry/utils) is included in ./issue-events-partitioned-name. 


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

in the ./scorecard folder

```bash
go run main.go --repo="<YOUR_REPO>" --commit="<COMMIT_HASH>" --checks="Maintained"
```

Options:

- `--repo` - The url of the project's github repository
- `--commit` - the commit hash on which you want to run the check
- `--checks` - the check you wish to run 
- `--format` - the desired format of the output (text, json)




