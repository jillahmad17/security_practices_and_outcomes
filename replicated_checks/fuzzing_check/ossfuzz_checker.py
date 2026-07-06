import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


class OSSFuzzRepoManager:
	"""Manages the OSS-Fuzz repository for historical lookups."""
	
	def __init__(self, base_dir: str = "./oss-fuzz-repo"):
		self.repo_url = "https://github.com/google/oss-fuzz.git"
		self.base_dir = Path(base_dir)
		self.base_dir.mkdir(parents=True, exist_ok=True)
		self.repo_path = self.base_dir / "oss-fuzz"
	
	def ensure_repo_exists(self) -> Path:
		"""Clone or update the OSS-Fuzz repository."""
		if not self.repo_path.exists():
			try:
				subprocess.run(
					["git", "clone", self.repo_url, str(self.repo_path)],
					check=True,
					capture_output=True,
					text=True,
					timeout=300
				)				
			except subprocess.CalledProcessError as e:
				raise RuntimeError(f"Failed to clone OSS-Fuzz: {e.stderr}")
			except subprocess.TimeoutExpired:
				raise RuntimeError("Timeout while cloning OSS-Fuzz repository")
		
		if not (self.repo_path / ".git").exists():
			raise RuntimeError(f"{self.repo_path} exists but is not a git repository")
		
		# Fetch latest changes
		try:
			subprocess.run(
				["git", "-C", str(self.repo_path), "fetch", "--all"],
				check=True,
				capture_output=True,
				text=True,
				timeout=120
			)
		except subprocess.CalledProcessError as e:
			pass
		
		return self.repo_path
	
	def checkout_closest_commit(self, target_date: datetime) -> str:
		try:
			result = subprocess.run(
				["git", "-C", str(self.repo_path), "log", "--all", 
				 "--since=2023-01-01", "--pretty=%H %cI"],
				capture_output=True,
				text=True,
				check=True,
				timeout=60
			)
			
			commits = []
			for line in result.stdout.splitlines():
				if not line.strip():
					continue
				parts = line.split(maxsplit=1)
				if len(parts) != 2:
					continue
				sha, date_str = parts
				commit_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
				commits.append((sha, commit_date))
			
			closest_sha = None
			for sha, commit_date in commits:
				if commit_date <= target_date:
					closest_sha = sha
					break
			
			if closest_sha is None:
				raise RuntimeError(f"No commit found before {target_date.isoformat()}")
			
			subprocess.run(
				["git", "-C", str(self.repo_path), "checkout", closest_sha],
				check=True,
				capture_output=True,
				text=True,
				timeout=60
			)
			
			return closest_sha
			
		except subprocess.CalledProcessError as e:
			raise RuntimeError(f"Failed to checkout commit: {e.stderr}")
		except subprocess.TimeoutExpired:
			raise RuntimeError("Timeout while checking out commit")


class OSSFuzzChecker:
	@staticmethod
	def normalize_github_url(url: str) -> str:
		url = url.lower()
		url = url.replace('https://', '').replace('http://', '')
		url = url.replace('www.', '')
		url = url.rstrip('/')
		url = url.replace('.git', '')
		if 'github.com/' in url:
			parts = url.split('github.com/')[-1].split('/')
			if len(parts) >= 2:
				return f"github.com/{parts[0]}/{parts[1]}"
		return url


	@staticmethod
	def search_package(repo_path: Path, github_repo_url: str) -> Tuple[bool, Optional[str]]:
		projects_dir = repo_path / "projects"
		if not projects_dir.exists():
			return False, None
		
		normalized_search = OSSFuzzChecker.normalize_github_url(github_repo_url)
		
		for project in projects_dir.iterdir():
			if not project.is_dir():
				continue
			
			yaml_file = project / "project.yaml"
			if not yaml_file.exists():
				continue
			
			try:
				with open(yaml_file, "r", encoding="utf-8", errors='ignore') as f:
					content = f.read().lower()
					
				# Normalize all URLs found in the yaml
				# Look for common URL patterns
				import re
				urls_in_yaml = re.findall(r'https?://[^\s<>"]+|github\.com/[^\s<>"]+', content)
				
				for yaml_url in urls_in_yaml:
					normalized_yaml = OSSFuzzChecker.normalize_github_url(yaml_url)
					if normalized_search == normalized_yaml:
						return True, project.name
						
			except Exception as e:
				continue
		
		return False, None