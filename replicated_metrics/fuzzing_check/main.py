import os
import argparse

from processor import FuzzingCheckOrchestrator

def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive fuzzing check: OSS-Fuzz, ClusterFuzzLite, and language-specific",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
		Examples:
		# Run all checks
		python main.py dataset.csv results.csv
		
		# With GitHub token for language detection
		python main.py dataset.csv results.csv --github-token ghp_xxxxx
		
		# Start fresh (ignore previous progress)
		python main.py dataset.csv results.csv --no-resume
		
		# Custom directories
		python main.py dataset.csv results.csv --repos-dir ./my_repos --ossfuzz-dir ./my_ossfuzz

		Output columns:
		- ossfuzz_check, ossfuzz_project, ossfuzz_error
		- cflite_check, cflite_error
		- lang_fuzzing (JSON), lang_error
				"""
    )
    
    parser.add_argument('input_csv', help='Input CSV file path')
    parser.add_argument('output_csv', help='Output CSV file path')
    parser.add_argument('--github-token', 
                       help='GitHub personal access token for language detection API',
                       default=os.environ.get('GITHUB_TOKEN'))
    parser.add_argument('--use-token-rotation', action='store_true',
                       help='Use multiple GitHub tokens (GITHUB_TOKEN_1, 2, 3) with rotation')
    parser.add_argument('--no-resume', action='store_true',
                       help='Start from scratch (ignore saved progress)')
    parser.add_argument('--repos-dir', default='./repos',
                       help='Directory for cloning repositories (default: ./repos)')
    parser.add_argument('--ossfuzz-dir', default='./oss-fuzz-repo',
                       help='Directory for OSS-Fuzz repository (default: ./oss-fuzz-repo)')
    parser.add_argument('--save-frequency', type=int, default=10,
                       help='Save progress every N rows (default: 10)')
    
    args = parser.parse_args()
    
    if args.use_token_rotation:
        print("Using token rotation mode with GITHUB_TOKEN_1, 2, 3")
    elif not args.github_token:
        print("Warning: No GitHub token provided. Language detection may be rate-limited.")
        print("Set GITHUB_TOKEN environment variable or use --github-token flag.")
        print("For high-volume processing, use --use-token-rotation with GITHUB_TOKEN_1, 2, 3")
    
    orchestrator = FuzzingCheckOrchestrator(
        repos_dir=args.repos_dir,
        ossfuzz_dir=args.ossfuzz_dir,
        github_token=args.github_token if not args.use_token_rotation else None,
        use_token_rotation=args.use_token_rotation,
        state_file="fuzzing_state.json",
        failure_log="fuzzing_failures.log"
    )
    
    try:
        orchestrator.process_dataset(
            input_csv=args.input_csv,
            output_csv=args.output_csv,
            resume=not args.no_resume,
            save_frequency=args.save_frequency
        )
    except KeyboardInterrupt:
        print("\nScript interrupted by user.")
    finally:
        orchestrator.cleanup()


if __name__ == "__main__":
    main()