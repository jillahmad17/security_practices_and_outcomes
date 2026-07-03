import re
import os
import time
import requests
import fnmatch
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from urllib.parse import urlparse

TOKEN_ROTATION_THRESHOLD = 50

class TokenManager:
	def __init__(self, token_range: Tuple[int, int] = (1, 4)):
		self.tokens = self._load_tokens(token_range)
		self.current_index = 0
		self.token_states = {}
		self._initialize_token_states()
	
	def _load_tokens(self, token_range: Tuple[int, int]) -> List[str]:
		tokens = []
		start, end = token_range
		
		for i in range(start, end):
			token = os.environ.get(f"GITHUB_TOKEN_{i}")
			if token:
				tokens.append(token)
		
		if not tokens:
			raise ValueError(f"No GitHub tokens found. Set GITHUB_TOKEN or GITHUB_TOKEN_{start}..{end-1}")
		
		return tokens
	
	def _check_rate_limit(self, token: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
		headers = {"Authorization": f"token {token}"}
		try:
			resp = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=10)
			if resp.status_code == 200:
				core = resp.json()["resources"]["core"]
				return core["remaining"], core["limit"], core["reset"]
		except Exception as e:
			print(f"Warning: Could not check rate limit: {e}")
		return None, None, None
	
	def _initialize_token_states(self):
		print(f"Initializing {len(self.tokens)} token(s)...")
		for i, token in enumerate(self.tokens):
			remaining, limit, reset = self._check_rate_limit(token)
			reset_time = datetime.fromtimestamp(reset) if reset else None
			is_valid = remaining is not None
			
			self.token_states[i] = {
				"token": token,
				"remaining": remaining or 0,
				"limit": limit or 5000,
				"reset": reset,
				"reset_time": reset_time,
				"is_valid": is_valid,
			}
	
	def get_active_token(self) -> str:
		state = self.token_states[self.current_index]
		
		# If current token is good, use it
		if state["is_valid"] and state["remaining"] > TOKEN_ROTATION_THRESHOLD:
			return state["token"]
		
		# Otherwise, rotate
		return self._rotate_token()
	
	def _rotate_token(self) -> str:
		for _ in range(len(self.tokens)):
			self.current_index = (self.current_index + 1) % len(self.tokens)
			state = self.token_states[self.current_index]
			
			remaining, limit, reset = self._check_rate_limit(state["token"])
			
			if remaining and remaining > TOKEN_ROTATION_THRESHOLD:
				state["remaining"] = remaining
				state["limit"] = limit
				state["reset"] = reset
				state["reset_time"] = datetime.fromtimestamp(reset) if reset else None
				return state["token"]
		return self._wait_for_reset()
	
	def _wait_for_reset(self) -> str:
		valid_states = [s for s in self.token_states.values() if s["reset"]]
		
		if not valid_states:
			time.sleep(60)
			return self.tokens[0]
		
		soonest = min(valid_states, key=lambda x: x["reset"])
		wait_sec = max(0, soonest["reset"] - time.time()) + 10
		
		time.sleep(wait_sec)
		
		for i, state in self.token_states.items():
			if state["token"] == soonest["token"]:
				remaining, limit, reset = self._check_rate_limit(state["token"])
				state["remaining"] = remaining or 0
				state["limit"] = limit or 5000
				state["reset"] = reset
				self.current_index = i
				return state["token"]
		
		return soonest["token"]
	
	def update_usage(self, used: int = 1):
		"""Update usage count for current token."""
		state = self.token_states[self.current_index]
		state["remaining"] = max(0, state["remaining"] - used)
	
	def log_stats(self):
		if not self.token_manager:
			return
		
		print("\n" + "="*60)
		print("GitHub Token Statistics")
		print("="*60)
		for i, s in self.token_manager.token_states.items():
			status = "OK" if s["is_valid"] and s["remaining"] > 0 else "EXHAUSTED"
			print(f"  [{status}] Token {i + 1}: {s['remaining']}/{s['limit']} remaining")
			if s['reset_time']:
				print(f"           Resets at: {s['reset_time']}")
		print("="*60 + "\n")

class LanguageSpec:
	def __init__(self, name: str, file_patterns: List[str], func_pattern: str, description: str):
		self.name = name
		self.file_patterns = file_patterns
		self.func_pattern = func_pattern
		self.description = description

def property_based_description(language: str) -> str:
	return (
		f"Property-based testing in {language} generates test instances randomly "
		"or exhaustively and tests that specific properties are satisfied."
	)

LANGUAGE_SPECS = {
	"go": {
		"file_patterns": ["*_test.go"],
		"func_pattern": r"func\s+Fuzz\w+\s*\(\w+\s+\*testing.F\)",
		"name": "BuiltInGo",
		"url": "https://go.dev/doc/fuzz/",
		"desc": "Go fuzzing intelligently walks through the source code to report failures and find vulnerabilities.",
	},
	"python": { 
		"file_patterns": ["*.py"],
		"func_pattern": r"import atheris",
		"name": "PythonAtheris",
		"desc": "Python fuzzing by way of Atheris",
	},
	"c": { 
		"file_patterns": ["*.c"],
		"func_pattern": r"LLVMFuzzerTestOneInput",
		"name": "CLibFuzzer",
		"desc": "Fuzzed with C LibFuzzer",
	},
	"c++": { 
		"file_patterns": ["*.cc", "*.cpp"],
		"func_pattern": r"LLVMFuzzerTestOneInput",
		"name": "CppLibFuzzer",
		"desc": "Fuzzed with cpp LibFuzzer",
	},
	"javascript": { 
		"file_patterns": ["*.js"],
		"func_pattern": r"(from\s+['\"](fast-check|@fast-check/(ava|jest|vitest))['\"]|require\(\s*['\"](fast-check|@fast-check/(ava|jest|vitest))['\"]\s*\))",
		"name": "PropertyBasedJavaScript",
		"desc": property_based_description("JavaScript"),
	},
	"typescript": { 
		"file_patterns": ["*.ts"],
		"func_pattern": r"(from\s+['\"](fast-check|@fast-check/(ava|jest|vitest))['\"]|require\(\s*['\"](fast-check|@fast-check/(ava|jest|vitest))['\"]\s*\))",
		"name": "PropertyBasedTypeScript",
		"desc": property_based_description("TypeScript"),
	},
	"rust": { 
		"file_patterns": ["*.rs"],
		"func_pattern": r"libfuzzer_sys",
		"name": "RustCargoFuzz",
		"desc": "Fuzzed with Cargo-fuzz",
	},
	"java": { 
		"file_patterns": ["*.java"],
		"func_pattern": r"com.code_intelligence.jazzer.api.FuzzedDataProvider;",
		"name": "JavaJazzerFuzzer",
		"desc": "Fuzzed with Jazzer fuzzer",
	},
	"swift": { 
		"file_patterns": ["*.swift"],
		"func_pattern": r"LLVMFuzzerTestOneInput",
		"name": "SwiftLibFuzzer",
		"desc": "Fuzzed with Swift LibFuzzer",
	},
	"erlang": { 
		"file_patterns": ["*.erl", "*.hrl"],
		"func_pattern": r'-include_lib\("(eqc|proper)/include/(eqc|proper).hrl"\)\.',
		"name": "PropertyBasedErlang",
		"desc": property_based_description("Erlang"),
	},
	"haskell": { 
		"file_patterns": ["*.hs", "*.lhs"],
		"func_pattern": r"import\s+(qualified\s+)?Test\.((Hspec|Tasty)\.)?(QuickCheck|Hedgehog|Validity|SmallCheck)",
		"name": "PropertyBasedHaskell",
		"desc": property_based_description("Haskell"),
	},
	"elixir": { 
		"file_patterns": ["*.ex", "*.exs"],
		"func_pattern": r"use\s+(PropCheck|ExUnitProperties)",
		"name": "PropertyBasedElixir",
		"desc": property_based_description("Elixir"),
	},
	"gleam": { 
		"file_patterns": ["*.gleam"],
		"func_pattern": r"import\s+qcheck",
		"name": "PropertyBasedGleam",
		"desc": property_based_description("Gleam"),
	},
}


class LanguageChecker:
	def __init__(self, github_token: Optional[str] = None, use_token_rotation: bool = True):		
		self.session = requests.Session()
		
		if use_token_rotation:
			self.token_manager = TokenManager()
			token = self.token_manager.get_active_token()
			self.session.headers.update({"Authorization": f"token {token}"})
		elif github_token:
			self.token_manager = None
			self.session.headers.update({"Authorization": f"token {github_token}"})
		else:
			self.token_manager = None			
	

	def get_prominent_languages(self, github_url: str) -> List[str]:
		try:
			parsed = urlparse(github_url)
			path_parts = parsed.path.strip('/').split('/')
			if len(path_parts) < 2:
				return []
			
			owner, repo = path_parts[0], path_parts[1].replace(".git", "")

			if self.token_manager:
				token = self.token_manager.get_active_token()
				self.session.headers.update({"Authorization": f"token {token}"})

			api_url = f"https://api.github.com/repos/{owner}/{repo}/languages"
			response = self.session.get(api_url, timeout=10)

			if self.token_manager:
				self.token_manager.update_usage(1)

			if self.token_manager and response.headers:
				try:
					remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
					limit = int(response.headers.get('X-RateLimit-Limit', 5000))
					reset = int(response.headers.get('X-RateLimit-Reset', 0))
					
					# Update the actual state from GitHub's response
					state = self.token_manager.token_states[self.token_manager.current_index]
					state['remaining'] = remaining
					state['limit'] = limit
					state['reset'] = reset
					state['reset_time'] = datetime.fromtimestamp(reset) if reset else None
				
				except Exception as e:
					pass

			if response.status_code == 404:
				return []
			elif response.status_code == 403:
				if self.token_manager:
					token = self.token_manager.get_active_token()
					self.session.headers.update({"Authorization": f"token {token}"})
					response = self.session.get(api_url, timeout=10)
					if response.status_code == 403:
						return []
				return []
			elif response.status_code != 200:
				return []
			
			languages = response.json()

			if not languages:
				return []
			
			total_loc = sum(languages.values())
			avg_loc = total_loc / len(languages)
			threshold = avg_loc / 4.0

			prominent = [lang.lower() for lang, loc in languages.items() if loc >= threshold]

			return prominent
		
		except Exception as e:			
			return []
		
	def check_language_fuzzing(self, repo_path: Path, languages: List[str]) -> Dict[str, bool]:
		results = {}
		
		for lang in languages:
			spec = LANGUAGE_SPECS.get(lang)
			if not spec:
				results[lang] = False
				continue

			found = self._search_for_pattern(repo_path, spec)
			results[lang] = found

		return results
	
	def _search_for_pattern(self, repo_path: Path, spec: Dict) -> bool:
		pattern = re.compile(spec["func_pattern"])

		# Get all files once
		all_files = [f for f in repo_path.rglob("*") if f.is_file()]
		
		for file_pattern in spec["file_patterns"]:
			try:
				for file_path in all_files:
					if not fnmatch.fnmatch(file_path.name.lower(), file_pattern.lower()):
						continue
					try:
						with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
							content = f.read()
							if pattern.search(content):
								return True
					except Exception:
						continue
			except Exception as e:
				pass
		return False
	
	def log_token_stats(self):
		if self.token_manager:
			self.token_manager.log_stats()