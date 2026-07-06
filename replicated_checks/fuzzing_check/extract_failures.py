import csv
import sys
import re
from collections import defaultdict

def parse_failure_log(failure_file):
    unique_urls = set()
    
    with open(failure_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            # Extract URL from format: "Row X | URL @ SHA | Error"
            # Pattern: anything after "| " and before " @ "
            match = re.search(r'\|\s+(https?://[^\s]+)\s+@', line)
            if match:
                url = match.group(1)
                unique_urls.add(url)
            else:
                # Try alternative parsing if format is different
                parts = line.split('|')
                if len(parts) >= 2:
                    # Extract URL from second part
                    url_part = parts[1].strip()
                    url_match = re.search(r'(https?://[^\s]+)', url_part)
                    if url_match:
                        unique_urls.add(url_match.group(1))
    
    return sorted(unique_urls)

def extract_rows_by_urls(dataset_file, output_file, target_urls):
    """
    Extract all rows from dataset that match the target URLs.
    
    Args:
        dataset_file: Path to original CSV dataset
        output_file: Path to output CSV file
        target_urls: Set of URLs to extract
    """
    # Convert to set for faster lookup
    url_set = set(target_urls)
    
    rows_by_url = defaultdict(list)
    total_rows_extracted = 0
    
    with open(dataset_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        
        # Read and save header
        header = next(reader)
        
        # Process each row
        for row_num, row in enumerate(reader, start=2):  # start=2 because header is row 1
            if len(row) < 2:
                continue
            
            repo_url = row[0].strip()
            
            # Check if this URL is in our target set
            if repo_url in url_set:
                rows_by_url[repo_url].append(row)
                total_rows_extracted += 1
    
    # Write extracted rows to output file
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write header
        writer.writerow(header)
        
        # Write rows grouped by URL for easier reading
        for url in sorted(rows_by_url.keys()):
            for row in rows_by_url[url]:
                writer.writerow(row)
    
    # Print summary
    print(f"\nExtraction Summary:")
    print(f"{'='*60}")
    print(f"Unique repositories found in failures: {len(target_urls)}")
    print(f"Total rows extracted: {total_rows_extracted}")
    print(f"\nRows per repository:")
    for url in sorted(rows_by_url.keys()):
        print(f"  {url}: {len(rows_by_url[url])} rows")
    print(f"\nOutput written to: {output_file}")

def main():
    if len(sys.argv) != 4:
        print("Usage: python extract_failed_repos.py <failure_log> <original_dataset.csv> <output.csv>")
        print("\nExample:")
        print("  python extract_failed_repos.py failures.txt dataset.csv failed_repos.csv")
        print("\nFailure log format:")
        print("  Row 3722 | https://github.com/user/repo @ sha | Error message")
        sys.exit(1)
    
    failure_file = sys.argv[1]
    dataset_file = sys.argv[2]
    output_file = sys.argv[3]
    
    print("Step 1: Parsing failure log...")
    target_urls = parse_failure_log(failure_file)
    
    if not target_urls:
        print("ERROR: No repository URLs found in failure log!")
        print("Please check the format of your failure log.")
        sys.exit(1)
    
    print(f"Found {len(target_urls)} unique repository URLs with failures")
    
    print("\nStep 2: Extracting matching rows from dataset...")
    extract_rows_by_urls(dataset_file, output_file, target_urls)

if __name__ == "__main__":
    main()