#!/usr/bin/env python3
"""
Baseline runner for security audit benchmark.
Analyzes each repository in the dataset using an LLM to find vulnerabilities.
"""

import json
import os
import sys
import argparse
import logging
import tempfile
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from models import Dataset, Project, Vulnerability
from session_manager import SessionManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Finding:
    """Represents a security finding from the baseline analysis"""
    file_path: str
    severity: str  # high, medium, low, informational
    title: str
    description: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    confidence: float = 0.0  # 0.0 to 1.0
    
    def to_dict(self):
        return asdict(self)
    
    def hash(self) -> str:
        """Generate a hash for deduplication"""
        content = f"{self.file_path}:{self.title}:{self.severity}"
        return hashlib.md5(content.encode()).hexdigest()


class RepoDownloader:
    """Downloads repositories from various sources"""
    
    def __init__(self, cache_dir: str = None):
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / '.baseline_cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def download(self, repo_url: str, commit: str = None) -> Path:
        """Download a repository and return the path to the local directory"""
        
        # Generate cache key
        cache_key = hashlib.md5(f"{repo_url}:{commit or 'latest'}".encode()).hexdigest()
        repo_path = self.cache_dir / cache_key
        
        # Check if already cached
        if repo_path.exists():
            logger.info(f"Using cached repository: {repo_path}")
            return repo_path
        
        # Create directory
        repo_path.mkdir(parents=True, exist_ok=True)
        
        try:
            if 'github.com' in repo_url:
                self._download_github(repo_url, commit, repo_path)
            elif repo_url.endswith('.tar.gz') or repo_url.endswith('.tgz'):
                self._download_tarball(repo_url, repo_path)
            else:
                # Try git clone as fallback
                self._git_clone(repo_url, commit, repo_path)
            
            logger.info(f"Downloaded repository to: {repo_path}")
            return repo_path
            
        except Exception as e:
            logger.error(f"Failed to download {repo_url}: {e}")
            if repo_path.exists():
                shutil.rmtree(repo_path)
            raise
    
    def _download_github(self, repo_url: str, commit: str, dest_path: Path):
        """Download from GitHub using tarball URL"""
        # Extract owner and repo from URL
        match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
        if not match:
            raise ValueError(f"Invalid GitHub URL: {repo_url}")
        
        owner, repo = match.groups()
        if repo.endswith('.git'):
            repo = repo[:-4]
        
        # Use commit or default branch
        ref = commit or 'main'
        tarball_url = f"https://github.com/{owner}/{repo}/archive/{ref}.tar.gz"
        
        # Download and extract
        self._download_tarball(tarball_url, dest_path)
    
    def _download_tarball(self, url: str, dest_path: Path):
        """Download and extract a tarball"""
        import requests
        import tarfile
        
        # Download tarball
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp_file:
            for chunk in response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)
            tmp_path = tmp_file.name
        
        try:
            # Extract tarball
            with tarfile.open(tmp_path, 'r:gz') as tar:
                tar.extractall(dest_path)
            
            # Move contents up if extracted into subdirectory
            subdirs = list(dest_path.iterdir())
            if len(subdirs) == 1 and subdirs[0].is_dir():
                # Move contents up one level
                for item in subdirs[0].iterdir():
                    shutil.move(str(item), str(dest_path / item.name))
                subdirs[0].rmdir()
        finally:
            os.unlink(tmp_path)
    
    def _git_clone(self, repo_url: str, commit: str, dest_path: Path):
        """Clone a git repository"""
        # Clone the repository
        cmd = ['git', 'clone', '--depth', '1']
        if commit:
            cmd.extend(['--branch', commit])
        cmd.extend([repo_url, str(dest_path)])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Git clone failed: {result.stderr}")
        
        # Checkout specific commit if provided and not a branch
        if commit and len(commit) == 40:  # Likely a commit hash
            os.chdir(dest_path)
            subprocess.run(['git', 'fetch', '--depth', '1', 'origin', commit], check=True)
            subprocess.run(['git', 'checkout', commit], check=True)


class SourceFileAnalyzer:
    """Analyzes source files for security vulnerabilities using an LLM"""
    
    # File extensions by language
    LANGUAGE_EXTENSIONS = {
        'solidity': ['.sol'],
        'rust': ['.rs'],
        'go': ['.go'],
        'javascript': ['.js', '.ts', '.jsx', '.tsx'],
        'python': ['.py'],
        'cairo': ['.cairo'],
        'move': ['.move'],
        'vyper': ['.vy'],
    }
    
    def __init__(self, model: str = "gpt-5", api_key: str = None):
        self.model = model
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key not provided")
        
        # Initialize OpenAI client
        from openai import OpenAI
        self.client = OpenAI(api_key=self.api_key)
    
    def analyze_project(self, repo_path: Path, max_files: int = None) -> List[Finding]:
        """Analyze all source files in a project"""
        findings = []
        source_files = self._find_source_files(repo_path)
        
        if max_files:
            source_files = source_files[:max_files]
        
        logger.info(f"Found {len(source_files)} source files to analyze")
        
        # Analyze files in parallel with rate limiting
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for file_path in source_files:
                future = executor.submit(self._analyze_file, file_path, repo_path)
                futures.append((future, file_path))
                time.sleep(0.2)  # Rate limiting
            
            for future, file_path in futures:
                try:
                    file_findings = future.result(timeout=120)  # Increased timeout to 2 minutes
                    findings.extend(file_findings)
                    logger.info(f"Analyzed {file_path}: {len(file_findings)} findings")
                except Exception as e:
                    logger.error(f"Failed to analyze {file_path}: {e}")
                    import traceback
                    logger.debug(f"Traceback: {traceback.format_exc()}")
        
        return findings
    
    def _find_source_files(self, repo_path: Path) -> List[Path]:
        """Find all source files in the repository"""
        source_files = []
        
        # Determine language from files present
        for lang, extensions in self.LANGUAGE_EXTENSIONS.items():
            for ext in extensions:
                files = list(repo_path.rglob(f'*{ext}'))
                source_files.extend(files)
        
        # Filter out test files and dependencies
        filtered_files = []
        for file_path in source_files:
            path_str = str(file_path)
            # Skip test files, mocks, and dependencies
            if any(skip in path_str.lower() for skip in [
                'test', 'mock', 'node_modules', 'vendor', '.git',
                'lib/', 'libs/', 'dependencies/', 'build/', 'dist/',
                'target/', 'out/', '.deps'
            ]):
                continue
            filtered_files.append(file_path)
        
        return filtered_files
    
    def _analyze_file(self, file_path: Path, repo_path: Path) -> List[Finding]:
        """Analyze a single source file for vulnerabilities"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Skip very large files
            if len(content) > 100000:
                logger.warning(f"Skipping large file: {file_path}")
                return []
            
            # Determine language
            ext = file_path.suffix
            language = None
            for lang, extensions in self.LANGUAGE_EXTENSIONS.items():
                if ext in extensions:
                    language = lang
                    break
            
            if not language:
                return []
            
            # Create relative path
            relative_path = file_path.relative_to(repo_path)
            
            # Analyze with LLM
            findings = self._call_llm(content, str(relative_path), language)
            return findings
            
        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {str(e)}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return []
    
    def _call_llm(self, code: str, file_path: str, language: str) -> List[Finding]:
        """Call the LLM to analyze code for vulnerabilities"""
        
        prompt = f"""You are a security auditor analyzing {language} code for vulnerabilities.
Analyze the following code and identify security issues you are confident about.

File: {file_path}

Code:
```{language}
{code}
```

For each vulnerability found, provide:
1. Severity (high/medium/low/informational)
2. A clear, concise title
3. A brief description explaining the issue (1-2 sentences max, no proof of concept or extensive explanation)
4. The approximate line numbers if possible
5. Your confidence level (0.0 to 1.0)

IMPORTANT INSTRUCTIONS:
- Only report issues you are HIGHLY confident about (confidence > 0.7)
- Keep descriptions brief and concise (1-2 sentences)
- NO false positives - only report definite vulnerabilities
- Focus on real security vulnerabilities, not code quality issues
- No proof of concept code or extensive explanations needed

Respond in JSON format:
{{
  "findings": [
    {{
      "severity": "high|medium|low|informational",
      "title": "Clear vulnerability title",
      "description": "Brief 1-2 sentence explanation",
      "line_start": 10,
      "line_end": 15,
      "confidence": 0.85
    }}
  ]
}}

If no vulnerabilities are found, return an empty findings array."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a security auditor specializing in smart contract and blockchain security."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            # Parse response
            result = json.loads(response.choices[0].message.content)
            
            # Debug logging
            logger.debug(f"LLM response for {file_path}:")
            logger.debug(f"Raw findings: {json.dumps(result, indent=2)}")
            
            # Convert to Finding objects
            findings = []
            total_raw_findings = len(result.get('findings', []))
            filtered_count = 0
            
            for finding_data in result.get('findings', []):
                confidence = finding_data.get('confidence', 0)
                
                # Log what's being filtered
                if confidence < 0.7:
                    filtered_count += 1
                    logger.debug(f"Filtered out finding due to low confidence ({confidence}): {finding_data.get('title', 'Unknown')}")
                    continue
                
                finding = Finding(
                    file_path=file_path,
                    severity=finding_data.get('severity', 'medium'),
                    title=finding_data.get('title', 'Unknown Issue'),
                    description=finding_data.get('description', ''),
                    line_start=finding_data.get('line_start'),
                    line_end=finding_data.get('line_end'),
                    confidence=finding_data.get('confidence', 0.7)
                )
                findings.append(finding)
            
            logger.info(f"File {file_path}: {total_raw_findings} raw findings, {filtered_count} filtered, {len(findings)} kept")
            
            return findings
            
        except Exception as e:
            logger.error(f"LLM call failed for {file_path}: {str(e)}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return []


class VulnerabilityDeduplicator:
    """Deduplicates and consolidates findings"""
    
    @staticmethod
    def deduplicate(findings: List[Finding]) -> List[Finding]:
        """Remove duplicate findings based on similarity"""
        if not findings:
            return []
        
        # Group by hash
        unique_findings = {}
        for finding in findings:
            hash_key = finding.hash()
            if hash_key not in unique_findings:
                unique_findings[hash_key] = finding
            else:
                # Keep the one with higher confidence
                if finding.confidence > unique_findings[hash_key].confidence:
                    unique_findings[hash_key] = finding
        
        # Further deduplicate by title similarity
        final_findings = []
        seen_titles = set()
        
        for finding in sorted(unique_findings.values(), key=lambda x: x.confidence, reverse=True):
            # Normalize title for comparison
            normalized_title = re.sub(r'[^a-z0-9]+', '', finding.title.lower())
            
            if normalized_title not in seen_titles:
                seen_titles.add(normalized_title)
                final_findings.append(finding)
        
        return final_findings


class BaselineRunner:
    """Main runner for baseline generation"""
    
    def __init__(self, dataset_path: str, output_dir: str, model: str = "gpt-5", 
                 cache_dir: str = None, max_files_per_project: int = None,
                 session_dir: str = None, resume: bool = True):
        self.dataset_path = Path(dataset_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.model = model
        self.max_files = max_files_per_project
        self.resume = resume
        
        self.downloader = RepoDownloader(cache_dir)
        self.analyzer = SourceFileAnalyzer(model=model)
        self.deduplicator = VulnerabilityDeduplicator()
        
        # Initialize session manager
        session_dir = session_dir or self.output_dir / '.session'
        self.session_manager = SessionManager(session_dir)
        
        # Load dataset
        with open(self.dataset_path, 'r') as f:
            dataset_dict = json.load(f)
            self.dataset = Dataset(
                dataset_id=dataset_dict['dataset_id'],
                period_start=dataset_dict.get('period_start', ''),
                period_end=dataset_dict.get('period_end', ''),
                schema_version=dataset_dict.get('schema_version', '1.0.0')
            )
            # Reconstruct projects
            for project_data in dataset_dict.get('projects', []):
                project = Project(
                    project_id=project_data['project_id'],
                    name=project_data['name'],
                    platform=project_data['platform']
                )
                project.codebases = project_data.get('codebases', [])
                project.vulnerabilities = project_data.get('vulnerabilities', [])
                self.dataset.projects.append(project)
    
    def run(self, project_filter: str = None, clear_session: bool = False):
        """Run baseline analysis on all projects in the dataset"""
        projects = self.dataset.projects
        
        if project_filter:
            projects = [p for p in projects if project_filter.lower() in p.name.lower()]
        
        # Handle session management
        if clear_session:
            self.session_manager.clear_session()
            logger.info("Cleared previous session")
        
        # Check for resume
        if self.resume and self.session_manager.get_resume_info()['has_session']:
            self.session_manager.print_resume_summary()
        
        # Start or resume session
        self.session_manager.start_session(
            str(self.dataset_path),
            str(self.output_dir),
            self.model,
            len(projects)
        )
        
        logger.info(f"Running baseline on {len(projects)} projects")
        
        results = {}
        
        # Load existing results if resuming
        summary_file = self.output_dir / 'baseline_summary.json'
        if summary_file.exists() and self.resume:
            with open(summary_file, 'r') as f:
                results = json.load(f)
        
        for project in projects:
            # Check if project should be skipped (already processed)
            if self.resume and self.session_manager.should_skip_project(project.project_id):
                logger.info(f"Skipping already processed project: {project.name}")
                continue
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Analyzing project: {project.name} ({project.project_id})")
            logger.info(f"Progress: {self.session_manager.get_progress_percentage():.1f}%")
            logger.info(f"{'='*60}")
            
            # Mark project as started
            self.session_manager.start_project(project.project_id, project.name)
            
            try:
                project_findings = self._analyze_project(project)
                
                # Save results
                output_file = self.output_dir / f"{project.project_id}_baseline.json"
                self._save_results(project, project_findings, output_file)
                
                results[project.project_id] = {
                    'status': 'success',
                    'findings_count': len(project_findings),
                    'output_file': str(output_file)
                }
                
                # Mark project as completed
                self.session_manager.complete_project(project.project_id, len(project_findings))
                
                logger.info(f"Found {len(project_findings)} vulnerabilities for {project.name}")
                
                # Save summary after each project
                with open(summary_file, 'w') as f:
                    json.dump(results, f, indent=2)
                
            except Exception as e:
                logger.error(f"Failed to analyze {project.name}: {e}")
                results[project.project_id] = {
                    'status': 'failed',
                    'error': str(e)
                }
                
                # Mark project as failed
                self.session_manager.fail_project(project.project_id, str(e))
                
                # Save summary after failure
                with open(summary_file, 'w') as f:
                    json.dump(results, f, indent=2)
        
        logger.info(f"\nBaseline generation complete. Summary saved to {summary_file}")
        return results
    
    def _analyze_project(self, project: Project) -> List[Finding]:
        """Analyze a single project"""
        all_findings = []
        
        # Process each codebase
        for codebase in project.codebases:
            repo_url = codebase.get('repo_url')
            commit = codebase.get('commit')
            
            if not repo_url:
                logger.warning(f"No repository URL for codebase: {codebase}")
                continue
            
            # Check if this codebase was already processed (for resume)
            progress = self.session_manager.state.get('current_project_progress', {})
            if repo_url in progress.get('codebases_completed', []):
                logger.info(f"Skipping already processed codebase: {repo_url}")
                continue
            
            try:
                # Download repository
                logger.info(f"Downloading repository: {repo_url}")
                repo_path = self.downloader.download(repo_url, commit)
                
                # Analyze source files
                logger.info(f"Analyzing source files...")
                findings = self.analyzer.analyze_project(repo_path, self.max_files)
                all_findings.extend(findings)
                
                # Mark codebase as completed
                self.session_manager.update_project_progress(codebase_url=repo_url)
                
            except Exception as e:
                logger.error(f"Failed to process codebase {repo_url}: {e}")
        
        # Deduplicate findings
        deduplicated = self.deduplicator.deduplicate(all_findings)
        
        return deduplicated
    
    def _save_results(self, project: Project, findings: List[Finding], output_file: Path):
        """Save analysis results in a format suitable for comparison"""
        
        # Prepare output data
        output_data = {
            'project_id': project.project_id,
            'project_name': project.name,
            'platform': project.platform,
            'analysis_date': datetime.now().isoformat(),
            'model': self.model,
            'findings_count': len(findings),
            'findings': [f.to_dict() for f in findings],
            # Include expected vulnerabilities for comparison
            'expected_vulnerabilities': project.vulnerabilities
        }
        
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description='Generate baseline security analysis for audit benchmark')
    
    parser.add_argument(
        'dataset',
        help='Path to the dataset JSON file'
    )
    
    parser.add_argument(
        '--output-dir',
        default='baseline_results',
        help='Directory to save baseline results (default: baseline_results)'
    )
    
    parser.add_argument(
        '--model',
        default='gpt-5',
        help='OpenAI model to use (default: gpt-5)'
    )
    
    parser.add_argument(
        '--cache-dir',
        help='Directory to cache downloaded repositories'
    )
    
    parser.add_argument(
        '--max-files',
        type=int,
        help='Maximum number of files to analyze per project'
    )
    
    parser.add_argument(
        '--project',
        help='Filter to run on specific project (partial name match)'
    )
    
    parser.add_argument(
        '--no-resume',
        action='store_true',
        help='Do not resume from previous session'
    )
    
    parser.add_argument(
        '--clear-session',
        action='store_true',
        help='Clear previous session and start fresh'
    )
    
    parser.add_argument(
        '--session-dir',
        help='Directory to store session state (default: output_dir/.session)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Check for API key
    if not os.getenv('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    # Run baseline
    runner = BaselineRunner(
        dataset_path=args.dataset,
        output_dir=args.output_dir,
        model=args.model,
        cache_dir=args.cache_dir,
        max_files_per_project=args.max_files,
        session_dir=args.session_dir,
        resume=not args.no_resume
    )
    
    results = runner.run(
        project_filter=args.project,
        clear_session=args.clear_session
    )
    
    # Print summary
    successful = sum(1 for r in results.values() if r['status'] == 'success')
    failed = sum(1 for r in results.values() if r['status'] == 'failed')
    
    print(f"\nSummary:")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    
    if successful > 0:
        total_findings = sum(r['findings_count'] for r in results.values() if r['status'] == 'success')
        print(f"  Total findings: {total_findings}")
        print(f"  Average findings per project: {total_findings / successful:.1f}")


if __name__ == '__main__':
    main()