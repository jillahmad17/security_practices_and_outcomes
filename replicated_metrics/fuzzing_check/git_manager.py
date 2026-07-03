import subprocess
import shutil
from pathlib import Path
from typing import Optional

class GitRepoManager:
	def __init__(self, repos_dir: str = "./repos"):
		self.repos_dir = Path(repos_dir)
		self.repos_dir.mkdir(exist_ok=True)
		self.current_repo_url = None
		self.current_repo_path = None

	def clone_or_update_repo(self, github_url: str) -> Path:
		if self.current_repo_url and self.current_repo_url != github_url:
			if self.current_repo_path and self.current_repo_path.exists():
				try:
					shutil.rmtree(self.current_repo_path)
				except Exception as e:
					pass
			self.current_repo_url = None
			self.current_repo_path = None

		repo_path = self.repos_dir / "current_repo"

		if not repo_path.exists():
			try:
				subprocess.run(
					['git', 'clone', github_url, str(repo_path)],
					check=True,
					capture_output=True,
					text=True,
					timeout=2400
				)
			except subprocess.TimeoutExpired:
				raise Exception(f"Timeout while cloning {github_url}")
			except subprocess.CalledProcessError as e:
				raise Exception(f"Failed to clone {github_url}: {e.stderr}")

		self.current_repo_url = github_url
		self.current_repo_path = repo_path
		return repo_path

	def checkout_commit(self, repo_path: Path, commit_sha: str) -> bool:
		try:
			subprocess.run(
				['git', 'checkout', "-f", commit_sha],
				cwd=repo_path,
				check=True,
				capture_output=True,
				text=True,
				timeout=120
			)
			return True
		except subprocess.TimeoutExpired:
			return False
		except subprocess.CalledProcessError as e:
			return False
		except Exception as e:
			return False
		
	
	def cleanup(self):
		if self.current_repo_path and self.current_repo_path.exists():
			print(f"Cleaning up: {self.current_repo_path}")
			try:
				shutil.rmtree(self.current_repo_path)
			except Exception as e:
				print(f"Warning: Could not clean up repo: {e}")