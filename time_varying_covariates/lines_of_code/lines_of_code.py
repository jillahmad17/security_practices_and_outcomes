import csv
import subprocess
import logging
import sys
import shutil
from pathlib import Path
from typing import Dict, Optional

logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(levelname)s - %(message)s',
	handlers=[
		logging.FileHandler('cloc_analysis.log'),
		logging.StreamHandler(sys.stdout)
	]
)

logger = logging.getLogger(__name__)


class ClocAnalyzer:
	def __init__(self, csv_file: str, output_base_dir: str = "cloc_results", repos_dir: str = "repos_cache"):
		self.csv_file = csv_file
		self.output_base_dir = Path(output_base_dir)
		self.repos_dir = Path(repos_dir)
		self.output_base_dir.mkdir(exist_ok=True)
		self.repos_dir.mkdir(exist_ok=True)
		
		self.progress_file = Path("cloc_progress.txt")
		self.processed = self._load_progress()
		self.failure_file = Path("cloc_failures.txt")
		self.failed_repos = set()
		self.current_repo = None
		self.cloc_failed_repos = set()
		self.failed_packages = set()
		self._load_failures() 

	def _load_progress(self) -> set:
		if self.progress_file.exists():
			with open(self.progress_file, "r") as f:
				return set(line.strip() for line in f)
		return set()
	
	def _load_failures(self):
		if self.failure_file.exists():
			with open(self.failure_file, "r") as f:
				for line in f:
					parts = line.strip().split("|")
					if len(parts) >= 4:
						github_url = parts[0]
						package_name = parts[2]
						reason = parts[4] if len(parts) > 4 else ""
						repo_name = self._get_repo_name(github_url)

						if "package_previously_failed" not in reason:
							self.failed_packages.add(package_name)

						if "clone_failed" in reason:
							self.failed_repos.add(repo_name)
						elif "cloc_failed" in reason or "timeout" in reason.lower():
							self.cloc_failed_repos.add(repo_name)

	def _save_progress(self, entry_id: str):
		with open(self.progress_file, "a") as f:
			f.write(f"{entry_id}\n")
		self.processed.add(entry_id)
	
	def _save_failure(self, github_url: str, commit_sha: str, package_name: str, tag_name: str, reason: str):
		with open(self.failure_file, "a") as f:
			f.write(f"{github_url}|{commit_sha}|{package_name}|{tag_name}|{reason}\n")

	def _get_repo_name(self, github_url: str) -> str:
		url = github_url.rstrip("/").replace(".git", "")
		parts = url.split("github.com/")[-1]
		return parts
	
	def _get_repo_local_path(self, repo_name: str) -> Path:
		safe_name = repo_name.replace("/", "__")
		return self.repos_dir / safe_name
	
	def _cleanup_repo(self, repo_path: Path):
		if repo_path.exists():
			logger.info(f"Cleaning up repository at {repo_path}")
			try:
				shutil.rmtree(repo_path)
			except Exception as e:
				logger.error(f"Failed to cleanup {repo_path}: {e}")
	
	def _clone_repo(self, github_url: str, repo_path: Path) -> bool:
		if repo_path.exists():
			logger.info(f"Repository already cloned at {repo_path}")
			return True
		
		try:
			logger.info(f"Cloning {github_url} to {repo_path}")
			result = subprocess.run(
				["git", "clone", "--progress", github_url, str(repo_path)],
				text=True,
				timeout=120
			)

			if result.returncode == 0:
				logger.info(f"Successfully cloned {github_url}")
				return True
			else:
				logger.error(f"Failed to clone {github_url}")
				return False
		except subprocess.TimeoutExpired:
			logger.error(f"Timeout while cloning {github_url}")
			return False
		except Exception as e:
			logger.error(f"Error cloning {github_url}: {e}")
			return False
	
	def _checkout_commit(self, repo_path: Path, commit_sha: str) -> bool:
		try:
			logger.info(f"Fetching latest changes in {repo_path}")
			subprocess.run(
				["git", "-C", str(repo_path), "fetch", "--all"],
				capture_output=True,
				text=True,
				timeout=120
			)
			
			logger.info(f"Checking out commit {commit_sha}")
			result = subprocess.run(
				["git", "-C", str(repo_path), "checkout", "-f", commit_sha],
				capture_output=True,
				text=True,
				timeout=30
			)

			if result.returncode == 0:
				logger.info(f"Successfully checked out {commit_sha}")
				return True
			else:
				logger.error(f"Failed to checkout {commit_sha}: {result.stderr}")
				return False
				
		except subprocess.TimeoutExpired:
			logger.error(f"Timeout while checking out {commit_sha}")
			return False
		except Exception as e:
			logger.error(f"Error checking out {commit_sha}: {e}")
			return False
		
	def _run_cloc(self, repo_path: Path, output_file: Path) -> bool:
		try:
			logger.info(f"Running cloc on {repo_path}")
			output_file.parent.mkdir(parents=True, exist_ok=True)

			with open(output_file, 'w') as f:
				result = subprocess.run(
					["cloc", str(repo_path), "--yaml"],
					stdout=f,
					stderr=subprocess.PIPE,
					text=True,
					timeout=600
				)

			if result.returncode == 0:
				logger.info(f"Successfully ran cloc, output saved to {output_file}")
				return True
			else:
				logger.error(f"cloc failed: {result.stderr}")
				if output_file.exists():
					output_file.unlink()
				return False
		except subprocess.TimeoutExpired:
			logger.error(f"Timeout while running cloc on {repo_path}")
			if output_file.exists():
				output_file.unlink()
			return False
		except Exception as e:
			logger.error(f"Error running cloc: {e}")
			if output_file.exists():
				output_file.unlink()
			return False
	
	def _get_output_path(self, repo_name: str, package_name: str, commit_sha: str) -> Path:
		owner_name = repo_name.split("/")[0]
		repo_name_only = repo_name.split("/")[1]
		safe_dir = f"{owner_name}__{repo_name_only}"
		dir_path = self.output_base_dir / safe_dir
		return dir_path / f"{commit_sha}.yaml"
	
	def process_entry(self, row: Dict[str, str]) -> bool:
		github_url = row['github_repo']
		commit_sha = row["tag_commit_sha"]
		package_name = row["package_name"]
		tag_name = row["tag_name"]

		entry_id = f"{github_url}|{commit_sha}"

		if entry_id in self.processed:
			logger.info(f"Skipping already processed: {package_name} @ {tag_name} ({commit_sha[:8]})")
			return True
		
		repo_name = self._get_repo_name(github_url)
		
		if repo_name in self.failed_repos:
			logger.info(f"Skipping entry from previously failed repo: {repo_name}")
			self._save_failure(github_url, commit_sha, package_name, tag_name, "repo_previously_failed")
			return False
		
		if repo_name in self.cloc_failed_repos:
			logger.warning(f"Repo {repo_name} has cloc failures, but will attempt this entry")

		if package_name in self.failed_packages:
			logger.info(f"Skipping entry from previously failed package: {package_name}")
			self._save_failure(github_url, commit_sha, package_name, tag_name, "package_previously_failed")
			return False
		
		logger.info(f"\n{'='*80}")
		logger.info(f"Processing: {package_name} @ {tag_name}")
		logger.info(f"Repo: {github_url}")
		logger.info(f"Commit: {commit_sha}")
		logger.info(f"{'='*80}")

		repo_name = self._get_repo_name(github_url)
		repo_path = self._get_repo_local_path(repo_name)
		output_file = self._get_output_path(repo_name, package_name, commit_sha)

		if output_file.exists():
			logger.info(f"Output already exists at {output_file}, skipping")
			self._save_progress(entry_id)
			return True
		
		if self.current_repo != repo_name:
			if self.current_repo is not None:
				old_repo_path = self._get_repo_local_path(self.current_repo)
				# self._cleanup_repo(old_repo_path)
			self.current_repo = repo_name
		
		if not self._clone_repo(github_url, repo_path):
			logger.error(f"Failed to clone repository, marking repo as failed")
			self.failed_repos.add(repo_name)
			self.failed_packages.add(package_name)
			self._save_failure(github_url, commit_sha, package_name, tag_name, "clone_failed")
			return False

		if not self._checkout_commit(repo_path, commit_sha):
			logger.error(f"Failed to checkout commit, skipping entry")
			self.failed_packages.add(package_name)
			self._save_failure(github_url, commit_sha, package_name, tag_name, "checkout_failed")
			return False
		
		if not self._run_cloc(repo_path, output_file):
			logger.error(f"Failed to run cloc, skipping entry")
			self.failed_packages.add(package_name)
			self._save_failure(github_url, commit_sha, package_name, tag_name, "cloc_failed")
			return False
		
		self._save_progress(entry_id)
		logger.info(f"Successfully processed entry, output at {output_file}")
		return True
	
	def process_all(self):
		try:
			with open(self.csv_file, "r") as f:
				reader = csv.DictReader(f)
				rows = list(reader)

			total = len(rows)
			logger.info(f"Found {total} entries to process")
			logger.info(f"Already processed: {len(self.processed)} entries")

			success_count = 0
			failure_count = 0

			for i, row in enumerate(rows, 1):
				logger.info(f"\nProcessing entry {i}/{total}")

				try:
					if self.process_entry(row):
						success_count += 1
					else:
						failure_count += 1
				except Exception as e:
					logger.error(f"Unexpected error processing entry: {e}", exc_info=True)
					self._save_failure(
						row['github_repo'],
						row['tag_commit_sha'],
						row['package_name'],
						row['tag_name'],
						f"unexpected_error: {str(e)}"
					)
					failure_count += 1
			
			if self.current_repo is not None:
				final_repo_path = self._get_repo_local_path(self.current_repo)
				# self._cleanup_repo(final_repo_path)
			
			logger.info(f"\n{'='*80}")
			logger.info(f"Processing complete!")
			logger.info(f"Total entries: {total}")
			logger.info(f"Successful: {success_count}")
			logger.info(f"Failed: {failure_count}")
			logger.info(f"{'='*80}")
		except Exception as e:
			logger.error(f"Fatal error: {e}", exc_info=True)
			raise

def main():
	csv_file = "partial_failures.csv"

	if not Path(csv_file).exists():
		logger.error(f"CSV file not found: {csv_file}")
		sys.exit(1)

	try:
		subprocess.run(["cloc", "--version"], capture_output=True, check=True)
	except (subprocess.CalledProcessError, FileNotFoundError):
		logger.error(f"cloc is not installed or not in PATH")
		logger.error("Please install cloc first")
		sys.exit(1)

	analyzer = ClocAnalyzer(csv_file)
	analyzer.process_all()

if __name__ == "__main__":
	main()