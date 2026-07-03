# Scorecard Data Collection Script using GitHub API

This script automates the collection of OpenSSF Scorecard data for multiple GitHub repositories. It processes package information from a CSV file, runs security scorecards on each repository at specific commit points, and saves the results in a structured format.

## Pre-requisites:
 - Python 3 (preferably 3.8+)
 - Scorecard CLI tool installed ([click here](https://scorecard.dev/) for more information)
 - GitHub tokens (preferably 3 tokens)

## Configuration and Installation steps [FIRST TIME ONLY]:
1. Create a virtual environment called venv. For more information on virtual environments, [click here](https://docs.python.org/3/library/venv.html)
2. Activate the virtual environment using `source venv/bin/activate`.
3. Install dependencies using `pip install -r requirements.txt`
4. Setup GitHub tokens in your shell configuration file (`~/.zshrc`, `~/.bashrc`, `~/.bashrc`, etc):
   ```bash
   export GITHUB_TOKEN_1=ghp_your_token_here
   export GITHUB_TOKEN_2=ghp_your_token_here
   export GITHUB_TOKEN_3=ghp_your_token_here

   export GITHUB_AUTH_TOKEN=$GITHUB_TOKEN_1
   ```
5. Reload your shell (whatever your configuration file is, replace it with .zshrc in the command below) 
   ```bash
   source ~/.zshrc
   ```
6. You can verify that the tokens have been set using the `echo` command.
7. Edit the following configuration_variables in [collect_data.py](collect_data.py).
   - CHUNK_SIZE: Number of rows processed per checkpoint (default: 50)
   - TOKEN_ROTATION_THRESHOLD: Rotate token when requests drop below this (default: 100)
   - file_name: Input CSV file path

## Steps to run [collect_data.py](collect_data.py):
 
 1. Activate virtual environment using `source venv/bin/activate`. NOTE: To verify if venv is active, you can use `which pip` and check the path.
 2. Run the script using `python collect_data.py`
 3. **To get more statistics of the script, please read [STATS.md](STATS.md).**

## Resume from interruption:

1. You can stop the script by simply pressing `Ctrl + C`.
2. Before you restart the script, go to [/checkpoints/row_metrics.csv](checkpoints/row_metrics.csv) and check the last row. 
3. Then go to the dataset (make a copy of it if you want to for safety) and remove the rows that are already processed from step 2 (from the top row to the package in the last row of step 2).
4. **Move or rename the [/data](data) and [/checkpoints](checkpoints) directories because the re-run of the script will make directories with the same name again.**
5. Run the script. data and checkpoints will be created again. You can merge all the data at the end.

### NOTE: If you don't want to interrupt a script in between, you can split you dataset into smaller sizes and run the script over and over again on every split. Go to [Starting Fresh](#starting-fresh) for more information.

## Dataset columns:

 - `github_repo`
- `tag_name`
- `tag_commit_sha`
- `published_at`
- `project_name`
- `package_name`


## Output

### Data Files
- `data/` - JSON files with scorecard results
  - Format: `{project_name}__{package_name}.json`
  - Contains all versions for each package

### Checkpoint Files
- `checkpoints/chunk_XXXX.json` - Summary per chunk
- `checkpoints/failures.csv` - All failed attempts with reasons
- `checkpoints/row_metrics.csv` - Time and token usage per row
- `checkpoints/progress.json` - Resume state

## Monitoring

Watch for these in the output:

### Token Status (printed at each checkpoint)
```
Token Status:
  [OK] Token 1: 4523/5000 (resets: 2025-10-14 15:30:00)
  [LOW] Token 2: 89/5000 (resets: 2025-10-14 15:35:00)
  [OK] Token 3: 5000/5000 (resets: 2025-10-14 15:40:00)
```
- `[OK]` - Token healthy (>100 requests remaining)
- `[LOW]` - Token low but usable (1-100 requests)
- `[EXHAUSTED]` - Token depleted (0 requests)

### Checkpoint Summary (every 50 rows)
```
CHECKPOINT: Chunk 5 Complete
Chunk time: 125.34s
Chunk success: 48
Chunk failed: 2
```

### Token Rotation
```
[WARN] Token 1 low on requests. Only 95 remaining
[INFO] Rotating to next available token
[OK] Switched to Token 2
```

### Waiting for Reset
```
[ERROR] All tokens exhausted
[WAIT] Waiting 12.3 minutes for Token 2 to reset at 2025-10-14 15:45:00
```

## Starting Fresh

To completely reset and start over:

1. Delete checkpoint files: `rm -rf checkpoints/`

2. Optionally delete data files: `rm -rf data/`

3. Run the script: `python collect_data.py`

## Troubleshooting

### "No GitHub tokens found"
- Check tokens are set: `echo $GITHUB_TOKEN_1`
- Reload shell: `source ~/.zshrc`

### "[FAIL] Token X: Invalid or expired"
- Verify token is valid at https://github.com/settings/tokens
- Check token has required permissions

### Script hangs
- Scorecard subprocess may be stuck
- Wait for 300s timeout or press Ctrl+C
- Check `failures.csv` for error details

## Notes

- Token rotation is automatic
- Progress is saved after every chunk
- Failed entries are logged but don't stop processing
- All data files are appended (not overwritten)
