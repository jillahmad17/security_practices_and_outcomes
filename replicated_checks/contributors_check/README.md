# contributors_check

This is a  version of OpenSSF Scorecard that contains modifications to the contributors check. This check determines if there have been contributions from multiple organizations within the 30 most recent commits of a given moment in time specified by a commit hash.

./scorecard contains the modified version of OpenSSF Scorecard. ./custom-go-github contains a modified version of the github.com/google/go-github/v53 go module used by Scorecard.


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
go run main.go --repo="<YOUR_REPO>" --commit="<COMMIT_HASH>" --checks="Contributors"
```

Options:

- `--repo` - The url of the project's github repository
- `--commit` - the commit hash on which you want to run the check
- `--checks` - the check you wish to run 
- `--format` - the desired format of the output (text, json)




