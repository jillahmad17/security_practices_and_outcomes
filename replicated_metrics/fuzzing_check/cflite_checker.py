from pathlib import Path
from typing import Optional, Tuple


class CFLiteChecker:
    """Checks if a repository uses ClusterFuzzLite configuration."""
    
    @staticmethod
    def check_file_contains_commands(content: str, comment_char: str = "#") -> bool:
        """Check if file contains actual commands (non-comment, non-empty lines)."""
        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith(comment_char):
                return True
        return False
    
    @staticmethod
    def check(repo_path: Path) -> Tuple[bool, Optional[str]]:
        cflite_dockerfile = repo_path / ".clusterfuzzlite" / "Dockerfile"
        if cflite_dockerfile.exists():
            try:
                with open(cflite_dockerfile, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                has_commands = CFLiteChecker.check_file_contains_commands(content, "#")
                if has_commands:
                    return True, None
            except Exception as e:
                pass
        
        workflows_dir = repo_path / ".github" / "workflows"
        if workflows_dir.exists():
            for workflow_file in workflows_dir.glob("*.yml"):
                try:
                    with open(workflow_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read().lower()
                        if 'clusterfuzzlite' in content or 'cluster-fuzz-lite' in content:
                            return True, None
                except Exception:
                    continue
            
            for workflow_file in workflows_dir.glob("*.yaml"):
                try:
                    with open(workflow_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read().lower()
                        if 'clusterfuzzlite' in content or 'cluster-fuzz-lite' in content:
                            return True, None
                except Exception:
                    continue
        
        return False, None