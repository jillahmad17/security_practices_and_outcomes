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

- `--repo` - The url of the project's github repository
- `--commit` - the commit hash on which you want to run the check
- `--commit-date` - the date of the commit in ISO 8601 date and time format (YYYY-MM-DDT%HH:%MM:%SSZ)
- `--checks` - the check you wish to run 
- `--format` - the desired format of the output (text, json)




