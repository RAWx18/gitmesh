"""
Repository processor for generating Cosmos-compatible files from GitHub repositories.

This module provides functionality to clone repositories and generate the required files 
(content.md, tree.txt, summary, indexing_tree.txt) that can be stored in Redis for later use.
"""

import os
import tempfile
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
try:
    import git
except ImportError:
    # Fallback to subprocess for git operations
    git = None

logger = logging.getLogger(__name__)


class RepoProcessor:
    """
    Processes repositories to generate Cosmos-compatible files.
    """
    
    def __init__(self, model_name: str = "gpt-4o-mini"):
        """
        Initialize the repository processor.
        
        Args:
            model_name: Name of the model to use for processing
        """
        self.model_name = model_name
        self.temp_dirs = []
        
    def __del__(self):
        """Cleanup temporary directories on deletion."""
        self.cleanup()
        
    def cleanup(self):
        """Clean up temporary directories."""
        for temp_dir in self.temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logger.info(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup {temp_dir}: {e}")
        self.temp_dirs.clear()
    
    def clone_repository(self, repo_url: str, target_dir: str) -> bool:
        """
        Clone a repository to the target directory.
        
        Args:
            repo_url: URL of the repository to clone
            target_dir: Directory to clone into
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Cloning repository {repo_url} to {target_dir}")
            
            if git is not None:
                # Use GitPython if available
                git.Repo.clone_from(repo_url, target_dir, depth=1)
            else:
                # Fallback to subprocess
                result = subprocess.run(['git', 'clone', '--depth', '1', repo_url, target_dir], 
                                      capture_output=True, text=True, check=True)
                if result.returncode != 0:
                    raise Exception(f"Git clone failed: {result.stderr}")
            
            logger.info(f"Successfully cloned repository to {target_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clone repository {repo_url}: {e}")
            return False
    
    def get_all_files(self, repo_dir: str) -> List[str]:
        """
        Get all relevant files from the repository.
        
        Args:
            repo_dir: Repository directory
            
        Returns:
            List of file paths relative to repo_dir
        """
        files = []
        repo_path = Path(repo_dir)
        
        # Common patterns to include
        include_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.h', '.hpp',
            '.cs', '.go', '.rs', '.php', '.rb', '.swift', '.kt', '.scala', '.sh',
            '.sql', '.html', '.css', '.scss', '.less', '.vue', '.svelte',
            '.md', '.txt', '.yml', '.yaml', '.json', '.xml', '.toml', '.ini',
            '.dockerfile', '.env', '.gitignore', '.gitattributes'
        }
        
        # Common patterns to exclude
        exclude_dirs = {
            '.git', '__pycache__', 'node_modules', '.env', '.venv', 'venv',
            'dist', 'build', 'target', 'out', '.next', '.nuxt', 'coverage',
            '.pytest_cache', '.coverage', 'htmlcov', '.tox', '.mypy_cache'
        }
        
        for root, dirs, filenames in os.walk(repo_dir):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            root_path = Path(root)
            for filename in filenames:
                file_path = root_path / filename
                
                # Skip files that are too large (>1MB)
                try:
                    if file_path.stat().st_size > 1024 * 1024:
                        continue
                except:
                    continue
                
                # Include files with relevant extensions or important names
                if (file_path.suffix.lower() in include_extensions or
                    filename.lower() in {'readme', 'license', 'changelog', 'contributing',
                                       'makefile', 'dockerfile', 'requirements.txt',
                                       'package.json', 'setup.py', 'pyproject.toml'}):
                    
                    rel_path = file_path.relative_to(repo_path)
                    files.append(str(rel_path))
        
        return sorted(files)
    
    def generate_content_md(self, repo_dir: str, files: List[str]) -> str:
        """
        Generate content.md file with all file contents.
        
        Args:
            repo_dir: Repository directory
            files: List of files to include
            
        Returns:
            Content.md as string
        """
        content_lines = []
        repo_path = Path(repo_dir)
        
        for file_path in files:
            full_path = repo_path / file_path
            
            try:
                # Read file content
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    file_content = f.read()
                
                # Add file boundary
                content_lines.extend([
                    "=" * 48,
                    f"FILE: {file_path}",
                    "=" * 48,
                    file_content,
                    ""  # Empty line after file content
                ])
                
            except Exception as e:
                logger.warning(f"Failed to read file {file_path}: {e}")
                continue
        
        return "\n".join(content_lines)
    
    def generate_tree_txt(self, repo_dir: str, files: List[str]) -> str:
        """
        Generate tree.txt file with repository structure.
        
        Args:
            repo_dir: Repository directory
            files: List of files to include
            
        Returns:
            Tree.txt as string
        """
        # Build directory structure
        tree_lines = []
        directories = set()
        
        # Collect all directories
        for file_path in files:
            parts = Path(file_path).parts
            for i in range(len(parts)):
                dir_path = "/".join(parts[:i+1])
                if i < len(parts) - 1:  # Not the file itself
                    directories.add(dir_path)
        
        # Sort directories and files together
        all_items = list(directories) + files
        all_items.sort()
        
        for item in all_items:
            if item in directories:
                # Directory
                depth = item.count('/')
                indent = "  " * depth
                dir_name = Path(item).name
                tree_lines.append(f"{indent}{dir_name}/")
            else:
                # File
                depth = item.count('/')
                indent = "  " * depth
                file_name = Path(item).name
                tree_lines.append(f"{indent}{file_name}")
        
        return "\n".join(tree_lines)
    
    def generate_repo_map(self, repo_dir: str, files: List[str]) -> str:
        """
        Generate a simple repository map without complex dependencies.
        
        Args:
            repo_dir: Repository directory
            files: List of files to analyze
            
        Returns:
            Repository map as string
        """
        try:
            # Simple repository map showing file structure with basic info
            map_lines = ["Repository Structure:", ""]
            
            # Group files by directory
            dirs = {}
            for file_path in files:
                dir_path = str(Path(file_path).parent)
                if dir_path == '.':
                    dir_path = 'root'
                if dir_path not in dirs:
                    dirs[dir_path] = []
                dirs[dir_path].append(Path(file_path).name)
            
            # Generate map
            for dir_path in sorted(dirs.keys()):
                if dir_path != 'root':
                    map_lines.append(f"{dir_path}/")
                
                for filename in sorted(dirs[dir_path]):
                    full_path = os.path.join(repo_dir, dir_path if dir_path != 'root' else '', filename)
                    if dir_path == 'root':
                        full_path = os.path.join(repo_dir, filename)
                    
                    try:
                        # Get file size and basic info
                        stat = os.stat(full_path)
                        size = stat.st_size
                        if size < 1024:
                            size_str = f"{size}B"
                        elif size < 1024 * 1024:
                            size_str = f"{size//1024}KB"
                        else:
                            size_str = f"{size//(1024*1024)}MB"
                        
                        indent = "  " if dir_path != 'root' else ""
                        map_lines.append(f"{indent}{filename} ({size_str})")
                    except:
                        indent = "  " if dir_path != 'root' else ""
                        map_lines.append(f"{indent}{filename}")
                
                map_lines.append("")
            
            return "\n".join(map_lines)
            
        except Exception as e:
            logger.error(f"Failed to generate repository map: {e}")
            return ""
    
    def generate_summary(self, repo_dir: str, files: List[str]) -> str:
        """
        Generate repository summary.
        
        Args:
            repo_dir: Repository directory
            files: List of files
            
        Returns:
            Repository summary as string
        """
        repo_name = Path(repo_dir).name
        
        # Analyze file types
        file_types = {}
        total_files = len(files)
        
        for file_path in files:
            ext = Path(file_path).suffix.lower()
            if ext:
                file_types[ext] = file_types.get(ext, 0) + 1
        
        # Create summary
        summary_lines = [
            f"Repository: {repo_name}",
            f"Total files: {total_files}",
            "",
            "File types:"
        ]
        
        for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True):
            summary_lines.append(f"  {ext}: {count} files")
        
        # Add top-level structure
        summary_lines.extend([
            "",
            "Top-level structure:"
        ])
        
        top_level_items = set()
        for file_path in files:
            parts = Path(file_path).parts
            if parts:
                top_level_items.add(parts[0])
        
        for item in sorted(top_level_items):
            summary_lines.append(f"  {item}")
        
        return "\n".join(summary_lines)
    
    def process_repository(self, repo_url: str) -> Optional[Dict[str, str]]:
        """
        Process a repository and generate all required files.
        
        Args:
            repo_url: URL of the repository to process
            
        Returns:
            Dictionary with generated file contents:
            {
                'content': content.md content,
                'tree': tree.txt content, 
                'summary': summary content
            }
            Returns None if processing failed.
        """
        temp_dir = None
        
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix="cosmos_repo_")
            self.temp_dirs.append(temp_dir)
            
            logger.info(f"Processing repository: {repo_url}")
            
            # Clone repository
            if not self.clone_repository(repo_url, temp_dir):
                return None
            
            # Get all relevant files
            files = self.get_all_files(temp_dir)
            logger.info(f"Found {len(files)} files to process")
            
            if not files:
                logger.warning("No files found to process")
                return None
            
            # Generate content.md
            logger.info("Generating content.md...")
            content_md = self.generate_content_md(temp_dir, files)
            
            # Generate tree.txt
            logger.info("Generating tree.txt...")
            tree_txt = self.generate_tree_txt(temp_dir, files)
            
            # Generate summary
            logger.info("Generating summary...")
            summary = self.generate_summary(temp_dir, files)
            
            logger.info("Repository processing completed successfully")
            
            return {
                'content': content_md,
                'tree': tree_txt,
                'summary': summary
            }
            
        except Exception as e:
            logger.error(f"Failed to process repository {repo_url}: {e}")
            return None
        
        finally:
            # Cleanup is handled by __del__ method
            pass


def process_repository_for_redis(repo_url: str, model_name: str = "gpt-4o-mini") -> Optional[Dict[str, str]]:
    """
    Process a repository and generate files for Redis storage.
    
    Args:
        repo_url: URL of the repository to process
        model_name: Model name to use for processing
        
    Returns:
        Dictionary with generated file contents or None if failed
    """
    processor = RepoProcessor(model_name)
    try:
        return processor.process_repository(repo_url)
    finally:
        processor.cleanup()


if __name__ == "__main__":
    """Test the repository processor."""
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python repo_processor.py <repo_url>")
        sys.exit(1)
    
    repo_url = sys.argv[1]
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Process repository
    result = process_repository_for_redis(repo_url)
    
    if result:
        print("Repository processed successfully!")
        print(f"Content.md length: {len(result['content'])} characters")
        print(f"Tree.txt length: {len(result['tree'])} characters")
        print(f"Summary length: {len(result['summary'])} characters")
        print(f"Indexing tree length: {len(result['indexing_tree'])} characters")
    else:
        print("Failed to process repository")
        sys.exit(1)
