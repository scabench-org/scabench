#!/usr/bin/env python3
"""
ScaBench Source Code Checkout Tool
Downloads and checks out source code repositories at the exact commits specified in the dataset.
"""

import json
import subprocess
import sys
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import argparse
import shutil
from dataclasses import dataclass
from datetime import datetime

# Rich for better output
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


@dataclass
class CloneResult:
    """Result of a repository clone operation."""
    success: bool
    project_name: str
    repo_url: str
    commit: str
    target_dir: Path
    error_message: Optional[str] = None


class SourceCheckout:
    """Handles checking out source code from benchmark datasets."""
    
    def __init__(self, output_dir: str = "sources"):
        """Initialize the checkout tool."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results: List[CloneResult] = []
    
    @staticmethod
    def sanitize_name(name: str) -> str:
        """Sanitize project name for use as directory name."""
        # Replace only truly problematic characters for filesystems
        # Note: hyphens and dots are perfectly safe and should be preserved
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', ' ']
        sanitized = name
        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')
        # Remove multiple consecutive underscores
        while '__' in sanitized:
            sanitized = sanitized.replace('__', '_')
        return sanitized.strip('_').lower()
    
    def clone_repository(self, repo_url: str, commit: str, target_dir: Path, 
                        project_name: str) -> CloneResult:
        """Clone a repository and checkout the specified commit.
        
        Args:
            repo_url: GitHub repository URL
            commit: Commit hash to checkout
            target_dir: Target directory for the clone
            project_name: Name of the project for reporting
            
        Returns:
            CloneResult with operation status
        """
        try:
            # Skip if directory already exists and has correct commit
            if target_dir.exists():
                # Check if we're at the right commit
                current_commit = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=target_dir,
                    capture_output=True,
                    text=True
                ).stdout.strip()
                
                if current_commit.startswith(commit[:8]):
                    console.print(f"  [green]✓[/green] Already at correct commit: {target_dir.name}")
                    return CloneResult(True, project_name, repo_url, commit, target_dir)
                else:
                    # Remove and re-clone to get correct commit
                    console.print(f"  [yellow]⟳[/yellow] Wrong commit, re-cloning...")
                    shutil.rmtree(target_dir)
            
            # Ensure HTTPS URL
            if repo_url.startswith("git@github.com:"):
                repo_url = repo_url.replace("git@github.com:", "https://github.com/")
            elif repo_url.startswith("ssh://git@github.com/"):
                repo_url = repo_url.replace("ssh://git@github.com/", "https://github.com/")
            
            # Environment to disable credential prompts
            env = os.environ.copy()
            env['GIT_TERMINAL_PROMPT'] = '0'
            env['GIT_ASKPASS'] = 'echo'
            
            console.print(f"  [cyan]→[/cyan] Cloning {repo_url[:50]}...")
            
            # Clone with shallow history first
            result = subprocess.run(
                ["git", "-c", "credential.helper=", "clone", 
                 "--quiet", "--depth", "50", repo_url, str(target_dir)],
                capture_output=True,
                text=True,
                timeout=120,
                env=env
            )
            
            if result.returncode != 0:
                error_msg = f"Clone failed: {result.stderr[:200]}"
                console.print(f"  [red]✗[/red] {error_msg}")
                return CloneResult(False, project_name, repo_url, commit, 
                                 target_dir, error_msg)
            
            # Checkout the specific commit
            if commit:
                console.print(f"  [cyan]→[/cyan] Checking out commit {commit[:8]}...")
                
                # Try checkout
                result = subprocess.run(
                    ["git", "checkout", "--quiet", commit],
                    cwd=target_dir,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    # Fetch more history if needed
                    console.print(f"  [yellow]⟳[/yellow] Fetching full history...")
                    subprocess.run(
                        ["git", "fetch", "--unshallow", "--quiet"],
                        cwd=target_dir,
                        capture_output=True,
                        text=True,
                        timeout=180,
                        env=env
                    )
                    
                    # Try checkout again
                    result = subprocess.run(
                        ["git", "checkout", "--quiet", commit],
                        cwd=target_dir,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if result.returncode != 0:
                        error_msg = f"Checkout failed for commit {commit[:8]}"
                        console.print(f"  [red]✗[/red] {error_msg}")
                        shutil.rmtree(target_dir)
                        return CloneResult(False, project_name, repo_url, commit,
                                         target_dir, error_msg)
            
            console.print(f"  [green]✓[/green] Success: {target_dir.name}")
            return CloneResult(True, project_name, repo_url, commit, target_dir)
            
        except subprocess.TimeoutExpired:
            error_msg = "Operation timed out"
            console.print(f"  [red]✗[/red] {error_msg}")
            if target_dir.exists():
                shutil.rmtree(target_dir)
            return CloneResult(False, project_name, repo_url, commit, 
                             target_dir, error_msg)
        except Exception as e:
            error_msg = str(e)
            console.print(f"  [red]✗[/red] Error: {error_msg}")
            if target_dir.exists():
                shutil.rmtree(target_dir)
            return CloneResult(False, project_name, repo_url, commit, 
                             target_dir, error_msg)
    
    def checkout_dataset(self, dataset_path: Path, 
                        project_filter: Optional[str] = None,
                        skip_existing: bool = False) -> Dict[str, Any]:
        """Checkout all repositories from a dataset.
        
        Args:
            dataset_path: Path to the dataset JSON file
            project_filter: Optional project name/ID to filter
            skip_existing: Skip repos that already exist at correct commit
            
        Returns:
            Dictionary with checkout statistics
        """
        # Load dataset
        console.print(f"[cyan]Loading dataset:[/cyan] {dataset_path}")
        with open(dataset_path, 'r') as f:
            projects = json.load(f)
        
        # Filter projects if requested
        if project_filter:
            projects = [p for p in projects 
                       if project_filter.lower() in p.get('project_id', '').lower() or
                          project_filter.lower() in p.get('name', '').lower()]
        
        if not projects:
            console.print(f"[yellow]No projects found matching filter: {project_filter}[/yellow]")
            return {"total": 0, "successful": 0, "failed": 0}
        
        console.print(f"[green]Found {len(projects)} project(s) to process[/green]\n")
        
        # Statistics
        total_repos = 0
        successful = 0
        failed = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
            transient=False
        ) as progress:
            
            task = progress.add_task(
                f"Checking out repositories...", 
                total=len(projects)
            )
            
            for project in projects:
                project_name = project.get("name", project.get("project_id", "Unknown"))
                project_id = project.get("project_id", self.sanitize_name(project_name))
                
                progress.print(f"\n[bold]{project_name}[/bold]")
                
                # Process each codebase
                codebases = project.get("codebases", [])
                if not codebases:
                    progress.print("  [yellow]⚠[/yellow] No codebases found")
                    progress.advance(task)
                    continue
                
                for codebase in codebases:
                    repo_url = codebase.get("repo_url", "")
                    commit = codebase.get("commit", "")
                    
                    if not repo_url:
                        progress.print("  [yellow]⚠[/yellow] No repository URL")
                        continue
                    
                    # Skip non-GitHub repos
                    if "github.com" not in repo_url:
                        progress.print(f"  [yellow]⚠[/yellow] Skipping non-GitHub: {repo_url}")
                        continue
                    
                    total_repos += 1
                    
                    # Create target directory name
                    repo_name = repo_url.split("/")[-1].replace(".git", "")
                    # Use project_id exactly as-is to maintain consistency
                    dir_name = project_id
                    if len(codebases) > 1:
                        # Add repo name if multiple codebases
                        dir_name = f"{dir_name}_{self.sanitize_name(repo_name)}"
                    target_dir = self.output_dir / dir_name
                    
                    # Clone the repository
                    result = self.clone_repository(
                        repo_url, commit, target_dir, project_name
                    )
                    self.results.append(result)
                    
                    if result.success:
                        successful += 1
                    else:
                        failed.append(result)
                
                progress.advance(task)
        
        return {
            "total": total_repos,
            "successful": successful,
            "failed": len(failed),
            "failed_details": failed
        }
    
    def print_summary(self, stats: Dict[str, Any]):
        """Print a summary of the checkout operation."""
        # Create summary table
        table = Table(title="Checkout Summary", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        
        table.add_row("Total Repositories", str(stats["total"]))
        table.add_row("Successfully Cloned", f"[green]{stats['successful']}[/green]")
        table.add_row("Failed", f"[red]{stats['failed']}[/red]")
        
        console.print("\n")
        console.print(table)
        
        # Show failed repos if any
        if stats["failed"] > 0:
            console.print("\n[red]Failed repositories:[/red]")
            for fail in stats["failed_details"]:
                console.print(f"  • {fail.project_name}: {fail.error_message}")
        
        console.print(f"\n[green]Sources checked out to:[/green] {self.output_dir.absolute()}/")


def main():
    parser = argparse.ArgumentParser(
        description="Checkout source code repositories from ScaBench dataset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Checkout all projects from default dataset
  %(prog)s
  
  # Checkout specific project
  %(prog)s --project vulnerable_vault
  
  # Use custom dataset and output directory
  %(prog)s --dataset my_dataset.json --output my_sources/
        """
    )
    
    parser.add_argument(
        '--dataset', '-d',
        default='../datasets/curated-2025-08-18.json',
        help='Path to dataset JSON file (default: ../datasets/curated-2025-08-18.json)'
    )
    parser.add_argument(
        '--output', '-o',
        default='sources',
        help='Output directory for source code (default: sources/)'
    )
    parser.add_argument(
        '--project', '-p',
        help='Filter to specific project name or ID'
    )
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip repositories that already exist at correct commit'
    )
    
    args = parser.parse_args()
    
    # Validate dataset path
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        console.print(f"[red]Error: Dataset not found: {dataset_path}[/red]")
        sys.exit(1)
    
    # Print header
    console.print(Panel.fit(
        "[bold cyan]ScaBench Source Checkout Tool[/bold cyan]\n"
        f"[dim]Dataset: {dataset_path.name}[/dim]",
        border_style="cyan"
    ))
    
    # Initialize checkout tool
    checkout = SourceCheckout(args.output)
    
    # Perform checkout
    try:
        stats = checkout.checkout_dataset(
            dataset_path,
            project_filter=args.project,
            skip_existing=args.skip_existing
        )
        
        # Print summary
        checkout.print_summary(stats)
        
        # Exit with error if all failed
        if stats["total"] > 0 and stats["successful"] == 0:
            sys.exit(1)
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()