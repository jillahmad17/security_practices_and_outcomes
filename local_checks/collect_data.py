import os
import json
import time
import requests
import subprocess
import pandas as pd
from tqdm import tqdm
from pathlib import Path
from functools import wraps
from datetime import datetime

# Configuration
CHUNK_SIZE = 50
TOKEN_ROTATION_THRESHOLD = 100
CHECKPOINT_DIR = Path("checkpoints")
OUTPUT_DIR = Path("data")


# Global tracking variables
timing_stats = []
failure_log = []
token_stats = []
row_metrics = []
failed_packages = set()  # Track packages that have failed to skip them


class TokenManager:
    def __init__(self):
        self.tokens = self._load_tokens()
        self.current_index = 0
        self.token_states = {}
        self._initialize_token_states()

    # Load the tokens from the environment file
    def _load_tokens(self):
        tokens = []
        for i in range(4, 7):
            token = os.environ.get(f"GITHUB_TOKEN_{i}")
            if token:
                tokens.append(token)

        if not tokens:
            raise ValueError(
                f"No GitHub tokens found. Set GITHUB_TOKEN_1, GITHUB_TOKEN_2, GITHUB_TOKEN_3 in your shell configuration file")

        return tokens

    # Initialize the state for all tokens before the script starts
    def _initialize_token_states(self):
        print(f"Initializing {len(self.tokens)} GitHub token...")

        for i, token in enumerate(self.tokens):
            remaining, limit, reset = self._check_rate_limit(token)

            if remaining is not None:
                reset_time = datetime.fromtimestamp(reset) if reset else None
                self.token_states[i] = {
                    'token': token,
                    'remaining': remaining,
                    'limit': limit,
                    'reset': reset,
                    'reset_time': reset_time,
                    'is_valid': True,
                    'total_used': 0
                }

                status = "[OK]" if remaining > TOKEN_ROTATION_THRESHOLD else "[LOW]"
                print(
                    f"{status} Token {i+1}: {remaining} / {limit} requests (resets: {reset_time})")
            else:
                self.token_states[i] = {
                    'token': token,
                    'remaining': 0,
                    'limit': 0,
                    'reset': None,
                    'reset_time': None,
                    'is_valid': False,
                    'total_used': 0
                }
                print(f"[FAIL] Token {i+1}: Invalid or expired")

        if not any(state['is_valid'] for state in self.token_states.values()):
            raise ValueError("No valid GitHub tokens found!")

        print(
            f"Token manager initialized with {len([s for s in self.token_states.values() if s['is_valid']])} valid token(s)")

    # Method to check the number of token points given a token
    def _check_rate_limit(self, token):
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            response = requests.get(
                "https://api.github.com/rate_limit", headers=headers)
            if response.status_code == 200:
                data = response.json()
                core = data['resources']['core']
                return core['remaining'], core['limit'], core['reset']
        except Exception as e:
            pass

        return None, None, None

    # Get an active token and rotate to the next one if the current one is invalid or has less points remaining
    def get_active_token(self):
        current_state = self.token_states[self.current_index]

        if current_state['is_valid'] and current_state['remaining'] > TOKEN_ROTATION_THRESHOLD:
            return current_state['token']

        print(
            f"[WARN] Token {self.current_index + 1} low on requests. Only {current_state['remaining']} remaining")
        print("[INFO] Rotating to next available token")

        return self._rotate_token()

    # Token rotation mechanism in this method
    def _rotate_token(self):
        original_index = self.current_index
        attempts = 0

        while attempts < len(self.tokens):
            self.current_index = (self.current_index + 1) % len(self.tokens)
            attempts += 1

            state = self.token_states[self.current_index]
            remaining, limit, reset = self._check_rate_limit(state['token'])

            if remaining is not None:
                state['remaining'] = remaining
                state['limit'] = limit
                state['reset'] = reset
                state['reset_time'] = datetime.fromtimestamp(
                    reset) if reset else None
                state['is_valid'] = True

            if remaining > TOKEN_ROTATION_THRESHOLD:
                print(f"[OK] Switched to Token {self.current_index + 1}")
                return state['token']

        print(f"[ERROR] All tokens exhausted")
        return self._wait_for_token_reset()

    # Wait for the earliest token to reset
    def _wait_for_token_reset(self):
        valid_states = [(i, s) for i, s in self.token_states.items()
                        if s['is_valid'] and s['reset']]

        if not valid_states:
            raise ValueError(f"No valid tokens with reset times available")

        earliest_index, earliest_state = min(
            valid_states, key=lambda x: x[1]['reset'])
        wait_time = earliest_state['reset'] - time.time()

        if wait_time > 0:
            reset_time = earliest_state['reset_time']
            print(
                f"[WAIT] Waiting {wait_time/60:.1f} minutes for Token {earliest_index + 1} to reset at {reset_time}")

        interval = min(60, wait_time / 10)

        for _ in range(int(wait_time / interval)):
            time.sleep(interval)
            remaining_wait = earliest_state['reset'] - time.time()
            if remaining_wait > 0:
                print(f"[WAIT] {remaining_wait/60:.1f} minutes remaining..")

        final_wait = earliest_state['reset'] - time.time()
        if final_wait > 0:
            time.sleep(final_wait + 5)

        self.current_index = earliest_index
        state = self.token_states[earliest_index]
        remaining, limit, reset = self._check_rate_limit(state['token'])

        if remaining is not None:
            state['remaining'] = remaining
            state['limit'] = limit
            state['reset'] = reset
            state['reset_time'] = datetime.fromtimestamp(
                reset) if reset else None
            print(
                f"\n[OK] Token {earliest_index + 1} reset: {remaining}/{limit} requests available")
            return state['token']
        else:
            raise ValueError(
                f"Token {earliest_index + 1} still unavailable after reset!")

    # Update the stats for a token
    def update_token_usage(self, tokens_used):
        state = self.token_states[self.current_index]
        state['remaining'] = max(0, state['remaining'] - tokens_used)
        state['total_used'] += tokens_used
        token_stats.append(tokens_used)

    # Get token summary
    def get_token_summary(self):
        summary = []
        for i, state in self.token_states.items():
            if state['is_valid']:
                status = "[OK]" if state['remaining'] > TOKEN_ROTATION_THRESHOLD else "[LOW]" if state['remaining'] > 0 else "[EXHAUSTED]"
                summary.append(
                    f"{status} Token {i+1}: {state['remaining']}/{state['limit']} (used: {state['total_used']})")
        return "\n".join(summary)


# Global token manager
token_manager = None


def track_performance(func):
    """Decorator to track time per function call"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result, inner_elapsed_time, tokens_consumed = func(*args, **kwargs)
        elapsed_time = time.time() - start_time

        # Track timing
        timing_stats.append(elapsed_time)

        # Calculate average
        avg_time = sum(timing_stats) / len(timing_stats)

        # Print per-row stats
        print(
            f"Done! Time taken: {elapsed_time:.2f}s (avg: {avg_time:.2f}s)\n")

        return result, elapsed_time, tokens_consumed
    return wrapper

# Append data to failure log


def log_failure(params, error_message):
    failure_log.append({
        'index': params['index'],
        'project_name': params['project_name'],
        'package_name': params['package_name'],
        'github_repo': params['github_repo'],
        'tag_name': params['tag_name'],
        'tag_commit_sha': params['tag_commit_sha'],
        'published_at': params['published_at'],
        'error_message': error_message,
        'timestamp': pd.Timestamp.now().isoformat()
    })

# Get the GitHub API rate limit status


def get_github_rate_limit(token):
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    try:
        response = requests.get(
            'https://api.github.com/rate_limit', headers=headers)
        if response.status_code == 200:
            data = response.json()
            core = data['resources']['core']
            return core['remaining'], core['limit'], core['reset']
        else:
            return None, None, None
    except Exception as e:
        return None, None, None

# Decorator to wrap the function


def track_github_tokens(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = token_manager.get_active_token()

        remaining_before, _, _ = get_github_rate_limit(token)
        result, elapsed_time = func(*args, token=token, **kwargs)
        remaining_after, limit, reset = get_github_rate_limit(token)

        tokens_used = 0
        if reset and remaining_before is not None and remaining_after is not None:
            tokens_used = remaining_before - remaining_after
            token_manager.update_token_usage(tokens_used)

            avg_tokens = sum(token_stats) / len(token_stats)
            reset_dt = datetime.fromtimestamp(reset)
            print(
                f"GitHub API tokens used: {tokens_used}, Average: {avg_tokens:.2f}, Remaining: {remaining_after}/{limit}, Reset: {reset_dt}")

        return result, elapsed_time, tokens_used
    return wrapper

# Read the input csv file


def read_input_csv_file(file_name, chunksize=None):
    if chunksize:
        return pd.read_csv(file_name, chunksize=chunksize)
    return pd.read_csv(file_name)

# This will return a file_name which will be <owner>_<package_name>.json


def get_file_name(project_name, package_name):
    project_name = project_name.replace("/", "_")
    package_name = package_name.replace("/", "_")
    return f"{project_name}__{package_name}.json"

# Return a dictionary to the main script after clean up


def process_commit(data, **params):
    # Removals
    for check in data['checks']:
        for key in ['documentation']:
            check.pop(key, None)
    data.pop('repo', None)

    # Additions
    data['index_from_csv'] = params['index']
    data['github_repo'] = params['github_repo']
    data['tag_name'] = params['tag_name']
    data['tag_commit_sha'] = params['tag_commit_sha']
    data['published_at'] = params['published_at']
    data['project_name'] = params['project_name']
    data['package_name'] = params['package_name']

    # Modifications
    data['run_timestamp'] = data.pop('date')
    data['scorecard_details'] = data.pop('scorecard')

    return data


@track_performance
@track_github_tokens
def run_scorecard(index, row, token=None):
    params = {
        'index': index,
        'github_repo': row['github_repo'],
        'tag_name': row['tag_name'],
        'tag_commit_sha': row['tag_commit_sha'],
        'published_at': row['published_at'],
        'project_name': row['project_name'],
        'package_name': row['package_name']
    }

    print(
        f"\nRunning for package = {params['package_name']} and SHA = {params['tag_commit_sha']}")
    try:
        env = os.environ.copy()
        env['GITHUB_AUTH_TOKEN'] = token

        result = subprocess.run(
            ["scorecard", "--repo", params['github_repo'], "--commit", params['tag_commit_sha'],
             "--format=json", "--show-details"],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
            env=env
        )
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            error_message = "JSON parse error"
            print(
                f"{error_message} for {params['package_name']} and tag {params['tag_name']}")
            log_failure(params, error_message)
            # Mark this package as failed
            failed_packages.add(params['package_name'])
            return None, params
        clean_data = process_commit(data, **params)
        return clean_data, params
    except subprocess.TimeoutExpired:
        error_message = "Scorecard timeout (60s)"
        print(
            f"{error_message} for {params['package_name']}, SHA: {params['tag_commit_sha']}")
        log_failure(params, error_message)
        # Mark this package as failed
        failed_packages.add(params['package_name'])
        return None, params
    except subprocess.CalledProcessError as e:
        error_message = f"Scorecard called process error. Return code: {e.returncode}."
        print(
            f"{error_message} for {params['package_name']}. SHA: {params['tag_commit_sha']}")
        log_failure(params, error_message)
        # Mark this package as failed
        failed_packages.add(params['package_name'])
        return None, params
    except Exception as e:
        error_message = f"Error output: {e}"
        print(
            f"Scorecard failed for {params['package_name']}. SHA: {params['tag_commit_sha']}")
        print(error_message)
        log_failure(params, error_message)
        # Mark this package as failed
        failed_packages.add(params['package_name'])
        return None, params


def save_batch_to_json(data_list, project_name, package_name):
    file_name = get_file_name(project_name, package_name)
    file_path = OUTPUT_DIR / file_name

    # Handle file create vs append
    if file_path.exists():
        with open(file_path, 'r') as f:
            existing_data = json.load(f)
        print(f"File {file_name} exists. Appending {len(data_list)} entries.")
    else:
        existing_data = []
        print(f"File {file_name} does not exist. Creating new file.")

    existing_data.extend(data_list)

    with open(file_path, 'w') as f:
        json.dump(existing_data, f, indent=2)


def save_checkpoint(chunk_num, chunk_time, chunk_success, chunk_failed, chunk_skipped):
    """Save checkpoint data after each chunk"""
    checkpoint_data = {
        'chunk_number': chunk_num,
        'chunk_time': chunk_time,
        'chunk_success': chunk_success,
        'chunk_failed': chunk_failed,
        'chunk_skipped': chunk_skipped,
        'timestamp': pd.Timestamp.now().isoformat(),
        'token_summary': token_manager.get_token_summary(),
        'failed_packages_count': len(failed_packages)
    }

    # Save chunk timing
    chunk_file = CHECKPOINT_DIR / f"chunk_{chunk_num:04d}.json"
    with open(chunk_file, 'w') as f:
        json.dump(checkpoint_data, f, indent=2)

    # Save failures (if any in this chunk)
    if failure_log:
        failure_df = pd.DataFrame(failure_log)
        failure_file = CHECKPOINT_DIR / "failures.csv"
        if failure_file.exists():
            # Append to existing
            existing_df = pd.read_csv(failure_file)
            failure_df = pd.concat(
                [existing_df, failure_df], ignore_index=True)
        failure_df.to_csv(failure_file, index=False)

    # Save row metrics (time and tokens per row)
    if row_metrics:
        metrics_df = pd.DataFrame(row_metrics)
        metrics_file = CHECKPOINT_DIR / "row_metrics.csv"
        if metrics_file.exists():
            # Append to existing
            existing_df = pd.read_csv(metrics_file)
            metrics_df = pd.concat(
                [existing_df, metrics_df], ignore_index=True)
        metrics_df.to_csv(metrics_file, index=False)

    # Save failed packages list
    failed_packages_file = CHECKPOINT_DIR / "failed_packages.json"
    with open(failed_packages_file, 'w') as f:
        json.dump(list(failed_packages), f, indent=2)

    # Print checkpoint summary
    print(f"\n{'='*60}")
    print(f"CHECKPOINT: Chunk {chunk_num} Complete")
    print(f"{'='*60}")
    print(f"Chunk time: {chunk_time:.2f}s")
    print(f"Chunk success: {chunk_success}")
    print(f"Chunk failed: {chunk_failed}")
    print(f"Chunk skipped: {chunk_skipped}")
    print(f"Total failed packages: {len(failed_packages)}")
    print(f"Token Status:")
    print(token_manager.get_token_summary())
    print(f"{'='*60}\n")


def process_row(index, row, current_batch, current_package_key, success_cntr, failed_cntr, skipped_cntr):
    file_key = (row['project_name'], row['package_name'])

    # Check if this package has already failed
    if row['package_name'] in failed_packages:
        print(
            f"\n[SKIP] Package {row['package_name']} has already failed. Skipping row {index}.")

        # Log as skipped
        params = {
            'index': index,
            'github_repo': row['github_repo'],
            'tag_name': row['tag_name'],
            'tag_commit_sha': row['tag_commit_sha'],
            'published_at': row['published_at'],
            'project_name': row['project_name'],
            'package_name': row['package_name']
        }
        log_failure(params, "Skipped - package previously failed")

        skipped_cntr += 1
        return current_batch, file_key, success_cntr, failed_cntr, skipped_cntr

    # If we encounter a new package, save the current batch
    if current_package_key is not None and file_key != current_package_key:
        if current_batch:
            print(
                f"New package detected. Saving the batch for {current_package_key[1]}")
            save_batch_to_json(
                current_batch, current_package_key[0], current_package_key[1])
        current_batch = []

    data, elapsed_time, tokens_used = run_scorecard(index, row)

    if data is not None:
        current_batch.append(data)
        success_cntr += 1

        # Log row metrics
        row_metrics.append({
            'index': index,
            'project_name': row['project_name'],
            'package_name': row['package_name'],
            'tag_commit_sha': row['tag_commit_sha'],
            'time_taken': elapsed_time,
            'tokens_used': tokens_used,
            'timestamp': pd.Timestamp.now().isoformat()
        })
    else:
        failed_cntr += 1

    return current_batch, file_key, success_cntr, failed_cntr, skipped_cntr


def load_previous_failed_packages():
    """Load previously failed packages from checkpoint if it exists"""
    failed_packages_file = CHECKPOINT_DIR / "failed_packages.json"
    if failed_packages_file.exists():
        with open(failed_packages_file, 'r') as f:
            previous_failed = json.load(f)
            failed_packages.update(previous_failed)
            print(
                f"[INFO] Loaded {len(previous_failed)} previously failed packages from checkpoint")
            return len(previous_failed)
    return 0


if __name__ == "__main__":
    # Initialize variables
    file_name = "data.csv"

    print(f"Configuration:")
    print(f"\nChunk size: {CHUNK_SIZE} rows")
    print(f"Checkpoints will be saved to: /{CHECKPOINT_DIR}")
    print()

    # Initialize token manager
    token_manager = TokenManager()

    # Create directories
    OUTPUT_DIR.mkdir(exist_ok=True)
    CHECKPOINT_DIR.mkdir(exist_ok=True)

    # Load previously failed packages if resuming
    prev_failed_count = load_previous_failed_packages()

    # Track the current package batch
    current_batch = []
    current_package_key = None
    success_cntr = 0
    failed_cntr = 0
    skipped_cntr = 0

    # Chunk tracking
    chunk_num = 0
    chunk_start_time = time.time()
    chunk_success = 0
    chunk_failed = 0
    chunk_skipped = 0

    # Read data in chunks
    print(f"\nProcessing in chunks of {CHUNK_SIZE} rows.")
    data_source = read_input_csv_file(file_name, chunksize=CHUNK_SIZE)

    # Track overall timing
    overall_start = time.time()

    # Process each chunk
    for chunk in data_source:
        chunk_num += 1
        chunk_start_time = time.time()
        chunk_success = 0
        chunk_failed = 0
        chunk_skipped = 0

        print(f"\n{'*'*60}")
        print(f"Starting Chunk {chunk_num} ({len(chunk)} rows)")
        print(f"{'*'*60}\n")

        for index, row in tqdm(chunk.iterrows(), total=len(chunk),
                               desc=f"Chunk {chunk_num}", unit="pkg"):
            prev_success = success_cntr
            prev_failed = failed_cntr
            prev_skipped = skipped_cntr

            current_batch, current_package_key, success_cntr, failed_cntr, skipped_cntr = process_row(
                index, row, current_batch, current_package_key, success_cntr, failed_cntr, skipped_cntr
            )

            # Track chunk-level counters
            if success_cntr > prev_success:
                chunk_success += 1
            if failed_cntr > prev_failed:
                chunk_failed += 1
            if skipped_cntr > prev_skipped:
                chunk_skipped += 1

        # Save checkpoint after each chunk
        chunk_time = time.time() - chunk_start_time
        save_checkpoint(chunk_num, chunk_time, chunk_success,
                        chunk_failed, chunk_skipped)

        # Clear chunk-specific data from global lists to save memory
        failure_log.clear()
        row_metrics.clear()

    # Save final batch
    if current_batch:
        print(f"Saving final batch for {current_package_key[1]}")
        save_batch_to_json(
            current_batch, current_package_key[0], current_package_key[1])

    overall_elapsed = time.time() - overall_start

    # Print final summary
    print(f"\n{'='*60}")
    print(f"{'Data collection complete':^60}")
    print(f"{'='*60}")
    print(f"Total processed: {success_cntr + failed_cntr + skipped_cntr}")
    print(f"Successful: {success_cntr}")
    print(f"Failed: {failed_cntr}")
    print(f"Skipped: {skipped_cntr}")
    print(f"Total failed packages: {len(failed_packages)}")
    print(f"Total chunks: {chunk_num}")
    print(f"Total time: {overall_elapsed:.2f}s ({overall_elapsed/60:.2f} min)")

    if timing_stats:
        avg_time = sum(timing_stats) / len(timing_stats)
        print(f"\nOverall avg time per row: {avg_time:.2f}s")

    if token_stats:
        total_tokens = sum(token_stats)
        avg_tokens = total_tokens / len(token_stats)
        print(f"Total tokens used: {total_tokens}")
        print(f"Average tokens per row: {avg_tokens:.1f}")

    print(f"{'='*60}\n")
