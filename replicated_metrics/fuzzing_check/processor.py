import pandas as pd
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from git_manager import GitRepoManager
from ossfuzz_checker import OSSFuzzRepoManager, OSSFuzzChecker
from cflite_checker import CFLiteChecker
from language_checker import LanguageChecker


class FuzzingCheckOrchestrator:
	def __init__(self, 
			repos_dir="./repos",
			ossfuzz_dir="./oss-fuzz-repo",
			github_token: Optional[str] = None,
			use_token_rotation: bool = False,
			state_file: str = "fuzzing_state.json",
			failure_log: str = "fuzzing_failures.log"
			):
		self.git_manager = GitRepoManager(repos_dir)
		self.ossfuzz_manager = OSSFuzzRepoManager(ossfuzz_dir)
		self.ossfuzz_checker = OSSFuzzChecker()
		self.cflite_checker = CFLiteChecker()
		self.language_checker = LanguageChecker(github_token, use_token_rotation)
		
		self.state_file = Path(state_file)
		self.failure_log = Path(failure_log)

		self.ossfuzz_repo_path = self.ossfuzz_manager.ensure_repo_exists()
		self._last_ossfuzz_date = None

	def calculate_fuzzing_score(self, ossfuzz: bool, cflite: bool, lang_fuzz: bool) -> int:
		"""Calculate fuzzing score: 10 if ANY fuzzer found, 0 otherwise."""
		has_any_fuzzer = ossfuzz or cflite or lang_fuzz
		return 10 if has_any_fuzzer else 0
	
	def log_failure(self, row_idx: int, row_data: Dict[str, Any], error: str):
		with open(self.failure_log, "a", encoding="utf-8") as f:
			repo = row_data.get("github_repo", "unknown")
			commit = row_data.get("tag_commit_sha", "unknown")[:7]
			f.write(f"Row {row_idx} | {repo} @ {commit} | {error}\n")


	def save_state(self, last_processed_idx: int):
		state = {
			"last_processed_idx": last_processed_idx,
			"timestamp": datetime.now().isoformat()
		}

		with open(self.state_file, "w") as f:
			json.dump(state, f, indent=2)

	def load_state(self) -> Optional[int]:
		if not self.state_file.exists():
			return None
		
		try:
			with open(self.state_file, "r") as f:
				state = json.load(f)
				return state.get("last_processed_idx")
		except Exception as e:
			print(f"Warning: Could not load state file: {e}")  # Fixed: added f-string
			return None
		
	def process_single_row(self, row: pd.Series, row_idx: int) -> Dict[str, Any]:
		result = {
			"ossfuzz_check": False,
			"ossfuzz_project": None,
			"ossfuzz_error": None,
			"cflite_check": False,
			"cflite_error": None,
			"lang_fuzzing": None,
			"lang_error": None,
		}

		# OSS-Fuzz check
		try:
			release_date = datetime.fromisoformat(row["published_at"])
			
			if (self._last_ossfuzz_date is None or 
				abs((release_date - self._last_ossfuzz_date).days) > 0):
				try:
					self.ossfuzz_manager.checkout_closest_commit(release_date)
					self._last_ossfuzz_date = release_date
				except Exception as e:
					result["ossfuzz_error"] = str(e)
					self.log_failure(row_idx, row.to_dict(), f"OSS-Fuzz checkout: {str(e)}")

			if not result["ossfuzz_error"]:
				found, project_name = self.ossfuzz_checker.search_package(
					self.ossfuzz_repo_path,
					row["github_repo"]
				)
				result["ossfuzz_check"] = found
				result["ossfuzz_project"] = project_name
					
		except Exception as e:
			result["ossfuzz_error"] = str(e)
			self.log_failure(row_idx, row.to_dict(), f"OSS-Fuzz: {str(e)}")

		# Clone & checkout repo
		try:
			repo_path = self.git_manager.clone_or_update_repo(row['github_repo'])
			
			if not self.git_manager.checkout_commit(repo_path, row["tag_commit_sha"]):
				result["cflite_error"] = "Checkout failed"
				result["lang_error"] = "Checkout failed"
				self.log_failure(row_idx, row.to_dict(), "Git checkout failed")
				return result
			
		except Exception as e:
			result["cflite_error"] = str(e)
			result["lang_error"] = str(e)
			self.log_failure(row_idx, row.to_dict(), f"Repo: {str(e)}")
			return result

		# ClusterFuzzLite check
		try:
			has_cflite, error = self.cflite_checker.check(repo_path)
			result["cflite_check"] = has_cflite
			result["cflite_error"] = error
			
			if error:
				self.log_failure(row_idx, row.to_dict(), f"CFL: {error}")
				
		except Exception as e:
			result["cflite_error"] = str(e)
			self.log_failure(row_idx, row.to_dict(), f"CFL: {str(e)}")

		# Language-specific fuzzing
		try:
			languages = self.language_checker.get_prominent_languages(row["github_repo"])
			
			if languages is None:
				raise Exception("GitHub API failed")
			
			if languages:
				lang_results = self.language_checker.check_language_fuzzing(repo_path, languages)
				result["lang_fuzzing"] = json.dumps(lang_results)
			else:
				result["lang_fuzzing"] = json.dumps({})
				
		except Exception as e:
			result["lang_error"] = str(e)
			self.log_failure(row_idx, row.to_dict(), f"Languages: {str(e)}")

		# Calculate final score
		lang_fuzz_any = False
		if result.get('lang_fuzzing'):
			try:
				lang_dict = json.loads(result['lang_fuzzing'])
				lang_fuzz_any = any(lang_dict.values())
			except:
				pass
		
		result['fuzzing_score'] = self.calculate_fuzzing_score(
			result['ossfuzz_check'],
			result['cflite_check'],
			lang_fuzz_any
		)
		
		# Summary (one line only)
		status = []
		if result['ossfuzz_check']:
			status.append(f"OSS-Fuzz:{result['ossfuzz_project']}")
		if result['cflite_check']:
			status.append("CFlite")
		if lang_fuzz_any:
			status.append("LangFuzz")
		
		status_str = " | ".join(status) if status else "None"
		print(f"  Score: {result['fuzzing_score']}/10 [{status_str}]")
		
		return result
	
	def process_dataset(self,
			input_csv: str,
			output_csv: str,
			resume: bool = True,
			save_frequency: int = 10):
		df = pd.read_csv(input_csv)

		if 'published_at' in df.columns and not resume:
			print("Sorting dataset by publication date for optimal OSS-Fuzz caching...")
			df = df.sort_values('published_at').reset_index(drop=True)

		# Get starting point
		start_idx = 0
		if resume and Path(output_csv).exists():
			print(f"Found existing output file: {output_csv}")
			existing_df = pd.read_csv(output_csv)
			processed_mask = existing_df["ossfuzz_check"].notna()
			if processed_mask.any():  # Fixed: typo "an()"
				start_idx = processed_mask.sum()
				print(f"Resuming from row {start_idx + 1}")
				df = existing_df
		else:
			df["ossfuzz_check"] = None
			df["ossfuzz_project"] = None
			df["ossfuzz_error"] = None
			df["cflite_check"] = None
			df["cflite_error"] = None
			df["lang_fuzzing"] = None
			df["lang_error"] = None
			df['fuzzing_score'] = None

		if resume:
			state_idx = self.load_state()
			if state_idx is not None and state_idx >= start_idx:
				start_idx = state_idx + 1
				print(f"Loaded state: resuming from row {start_idx + 1}")
		
		total_rows = len(df)
		print(f"\n{'='*80}")
		print(f"FUZZING CHECK ORCHESTRATOR")
		print(f"{'='*80}")
		print(f"Processing {total_rows - start_idx} rows (starting from row {start_idx + 1})")
		print(f"Checks: OSS-Fuzz, ClusterFuzzLite, Language-specific")
		print(f"Failure log: {self.failure_log}")
		print(f"Output file: {output_csv}")
		print(f"{'='*80}\n")

		try:
			for idx in range(start_idx, total_rows):
				row = df.iloc[idx]
				print(f"\n[{idx + 1}/{total_rows}] {row['project_name']} @ {row['tag_commit_sha'][:7]}")

				try:
					result = self.process_single_row(row, idx)  # Fixed: typo "proces"

					for key, value in result.items():
						df.at[idx, key] = value

				except KeyboardInterrupt:
					print("\n\nKeyboardInterrupt detected. Saving progress...")
					df.to_csv(output_csv, index=False)
					self.save_state(idx)
					print(f"Progress saved at row {idx + 1}. Resume by running again.")
					raise
					
				if (idx + 1) % save_frequency == 0:
					df.to_csv(output_csv, index=False)
					self.save_state(idx)
					print(f"Progress saved ({idx + 1}/{total_rows})")
		
		except KeyboardInterrupt:
			print("\nExiting...")
			return
		
		df.to_csv(output_csv, index=False)
		self.save_state(total_rows - 1)
		
		# Log token stats if using rotation
		self.language_checker.log_token_stats()

		self._print_summary(df, total_rows)
	
	def _print_summary(self, df: pd.DataFrame, total_rows: int):
		"""Print processing summary."""
		ossfuzz_found = df['ossfuzz_check'].sum()
		cflite_found = df['cflite_check'].sum()

		# Count rows with any language fuzzing
		lang_fuzzing_count = 0
		for val in df['lang_fuzzing'].dropna():
			try:
				lang_dict = json.loads(val)
				if any(lang_dict.values()):
					lang_fuzzing_count += 1
			except:
				pass
			
		errors = (df['ossfuzz_error'].notna() | 
				 df['cflite_error'].notna() | 
				 df['lang_error'].notna()).sum()
		
		print(f"\n{'='*80}")
		print(f"PROCESSING COMPLETE")
		print(f"{'='*80}")
		print(f"Total rows processed:     {total_rows}")
		print(f"In OSS-Fuzz:              {int(ossfuzz_found)} ({ossfuzz_found/total_rows*100:.1f}%)")
		print(f"Using ClusterFuzzLite:    {int(cflite_found)} ({cflite_found/total_rows*100:.1f}%)")
		print(f"Language-specific fuzz:   {lang_fuzzing_count} ({lang_fuzzing_count/total_rows*100:.1f}%)")
		print(f"Errors encountered:       {errors}")
		print(f"Failure log:              {self.failure_log}")
		print(f"{'='*80}")
	
	def cleanup(self):
		"""Clean up resources."""
		self.git_manager.cleanup()