#!/usr/bin/env python3
"""
ScaBench Baseline Runner
Official baseline security analyzer for ScaBench smart contract audit benchmarks.
"""

import json
import os
import sys
import argparse
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

# Rich for console output
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.table import Table
from rich import box

# OpenAI for analysis
from openai import OpenAI

console = Console()


class Severity(str, Enum):
    """Vulnerability severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class VulnerabilityType(str, Enum):
    """Common vulnerability types."""
    REENTRANCY = "reentrancy"
    ACCESS_CONTROL = "access control"
    INTEGER_OVERFLOW = "integer overflow/underflow"
    DIVISION_BY_ZERO = "division by zero"
    INPUT_VALIDATION = "input validation"
    DOS = "denial of service"
    NUMERIC_ERROR = "numeric error"
    LOGIC_ERROR = "logic error"
    OTHER = "other"


@dataclass
class Finding:
    """A security vulnerability finding."""
    title: str
    description: str
    vulnerability_type: str
    severity: str
    confidence: float
    location: str
    file: str
    id: str = ""
    reported_by_model: str = ""
    status: str = "proposed"
    
    def __post_init__(self):
        """Generate ID if not provided."""
        if not self.id:
            id_source = f"{self.file}:{self.title}"
            self.id = hashlib.md5(id_source.encode()).hexdigest()[:16]


@dataclass
class AnalysisResult:
    """Result from analyzing a project."""
    project: str
    timestamp: str
    files_analyzed: int
    files_skipped: int
    total_findings: int
    findings: List[Finding]
    token_usage: Dict[str, int]


class BaselineRunner:
    """Main baseline analysis runner."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the baseline runner with optional configuration."""
        self.config = config or {}
        self.model = self.config.get('model', 'gpt-5-mini')
        self.api_key = self.config.get('api_key') or os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError("OpenAI API key not provided. Set OPENAI_API_KEY environment variable.")
        
        self.client = OpenAI(api_key=self.api_key)
    
    def analyze_file(self, file_path: Path, content: str) -> tuple[List[Finding], int, int]:
        """Analyze a single file for security vulnerabilities.
        
        Returns:
            Tuple of (findings, input_tokens, output_tokens)
        """
        console.print(f"[dim]  → Analyzing {file_path.name} ({len(content)} bytes)[/dim]")
        
        system_prompt = """You are a security auditor analyzing smart contract code for vulnerabilities.

Analyze the provided code file and identify security vulnerabilities. For each vulnerability found, provide:

1. A clear title describing the issue
2. A detailed description including:
   - What the vulnerability is
   - Where it occurs (function name, line references)
   - Why it's a security issue
   - Potential impact
3. The vulnerability type (e.g., reentrancy, access control, integer overflow, etc.)
4. Severity level (critical, high, medium, low)
5. Confidence level (0.0 to 1.0)

Focus on REAL security issues that could lead to:
- Loss of funds
- Unauthorized access
- Denial of service
- Data corruption
- Privilege escalation
- Protocol manipulation

DO NOT report:
- Code quality issues without security impact
- Gas optimization suggestions unless they prevent DoS
- Style or naming convention issues
- Missing comments or documentation
- Theoretical issues without practical exploit paths

Return your findings as a JSON array. If no vulnerabilities found, return empty array: []

Example response:
[
  {
    "title": "Reentrancy vulnerability in withdraw function",
    "description": "The withdraw function sends ETH before updating state...",
    "vulnerability_type": "reentrancy",
    "severity": "high",
    "confidence": 0.9,
    "location": "withdraw() function, line 45"
  }
]"""

        user_prompt = f"""Analyze this {file_path.suffix} file for security vulnerabilities:

File: {file_path.name}
```{file_path.suffix[1:] if file_path.suffix else 'txt'}
{content}
```

Identify and report security vulnerabilities found."""

        try:
            # Add reasoning_effort for supported models
            extra_params = {}
            if self.model in ['gpt-5-mini', 'gpt-5']:
                extra_params['reasoning_effort'] = 'medium'
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                **extra_params
            )
            
            # Extract token usage
            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0
            
            # Parse response
            result = json.loads(response.choices[0].message.content)
            
            # Handle different response formats
            findings_data = []
            if isinstance(result, list):
                findings_data = result
            elif isinstance(result, dict):
                if 'findings' in result:
                    findings_data = result['findings']
                elif 'vulnerabilities' in result:
                    findings_data = result['vulnerabilities']
                elif 'title' in result:  # Single finding
                    findings_data = [result]
            
            # Convert to Finding objects
            findings = []
            for f_data in findings_data:
                finding = Finding(
                    title=f_data.get('title', 'Unknown'),
                    description=f_data.get('description', ''),
                    vulnerability_type=f_data.get('vulnerability_type', 'other'),
                    severity=f_data.get('severity', 'medium'),
                    confidence=f_data.get('confidence', 0.5),
                    location=f_data.get('location', 'unknown'),
                    file=str(file_path.name),
                    reported_by_model=self.model
                )
                findings.append(finding)
            
            if findings:
                console.print(f"[green]  → Found {len(findings)} vulnerabilities[/green]")
            else:
                console.print(f"[yellow]  → No vulnerabilities found[/yellow]")
            
            return findings, input_tokens, output_tokens
            
        except Exception as e:
            console.print(f"[red]Error analyzing {file_path.name}: {e}[/red]")
            return [], 0, 0
    
    def select_files_for_analysis(self, files: List[Path], max_files: int) -> List[Path]:
        """Intelligently select the most important files to analyze."""
        if len(files) <= max_files:
            return files
        
        console.print(f"[yellow]Selecting {max_files} most important files from {len(files)} total[/yellow]")
        
        # Priority patterns for smart contract security analysis
        priority_patterns = [
            # Core contracts
            ('*vault*', 100),
            ('*pool*', 95),
            ('*router*', 90),
            ('*treasury*', 85),
            ('*governance*', 80),
            
            # Security-critical
            ('*access*', 75),
            ('*oracle*', 75),
            ('*bridge*', 75),
            ('*proxy*', 70),
            ('*upgrade*', 70),
            
            # Token/DeFi
            ('*token*', 65),
            ('*stake*', 60),
            ('*reward*', 60),
            ('*swap*', 55),
            
            # Common patterns
            ('*core*', 50),
            ('*main*', 45),
            ('*factory*', 40),
            ('*registry*', 35),
        ]
        
        # Score files
        file_scores = []
        for file in files:
            score = 0
            file_lower = file.name.lower()
            
            # Check priority patterns
            for pattern, weight in priority_patterns:
                import fnmatch
                if fnmatch.fnmatch(file_lower, pattern):
                    score += weight
            
            # Penalize test/mock files
            if 'test' in file_lower or 'mock' in file_lower:
                score -= 100
            
            # Prefer contracts over libraries/interfaces
            if file.suffix == '.sol':
                with open(file, 'r', encoding='utf-8') as f:
                    content = f.read(1000)  # Check first 1000 chars
                    if 'contract ' in content:
                        score += 20
                    elif 'library ' in content:
                        score += 5
                    elif 'interface ' in content:
                        score -= 5
            
            file_scores.append((file, score))
        
        # Sort by score and select top files
        file_scores.sort(key=lambda x: x[1], reverse=True)
        selected = [f for f, _ in file_scores[:max_files]]
        
        console.print(f"[green]Selected {len(selected)} files based on security importance[/green]")
        return selected
    
    def analyze_project(self, 
                       project_name: str,
                       source_dir: Path,
                       max_files: Optional[int] = None,
                       file_patterns: Optional[List[str]] = None) -> AnalysisResult:
        """Analyze a project for security vulnerabilities.
        
        Args:
            project_name: Name of the project
            source_dir: Directory containing source files
            max_files: Maximum number of files to analyze (None = all)
            file_patterns: List of glob patterns for files to analyze
            
        Returns:
            AnalysisResult with findings
        """
        console.print(f"\n[bold cyan]Analyzing project: {project_name}[/bold cyan]")
        
        # Find files to analyze
        if file_patterns:
            files = []
            for pattern in file_patterns:
                files.extend(source_dir.glob(pattern))
        else:
            # Default to common smart contract patterns
            patterns = ['**/*.sol', '**/*.vy', '**/*.cairo', '**/*.rs']
            files = []
            for pattern in patterns:
                files.extend(source_dir.glob(pattern))
        
        # Remove duplicates and filter
        files = list(set(files))
        files = [f for f in files if f.is_file() and 'test' not in f.name.lower()]
        
        if not files:
            console.print(f"[yellow]No files found to analyze[/yellow]")
            return AnalysisResult(
                project=project_name,
                timestamp=datetime.now().isoformat(),
                files_analyzed=0,
                files_skipped=0,
                total_findings=0,
                findings=[],
                token_usage={'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
            )
        
        # Select files if limit specified
        if max_files and len(files) > max_files:
            files = self.select_files_for_analysis(files, max_files)
        
        console.print(f"[dim]Found {len(files)} files to analyze[/dim]")
        
        # Analyze files
        all_findings = []
        files_analyzed = 0
        files_skipped = 0
        total_input_tokens = 0
        total_output_tokens = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
            transient=False
        ) as progress:
            task = progress.add_task(f"Analyzing {len(files)} files...", total=len(files))
            
            for file_path in files:
                progress.update(task, description=f"Analyzing {file_path.name}...")
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    if not content.strip():
                        files_skipped += 1
                        progress.advance(task)
                        continue
                    
                    findings, input_tokens, output_tokens = self.analyze_file(file_path, content)
                    all_findings.extend(findings)
                    files_analyzed += 1
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    
                except Exception as e:
                    console.print(f"[red]Error processing {file_path.name}: {e}[/red]")
                    files_skipped += 1
                
                progress.advance(task)
        
        # Deduplicate findings
        unique_findings = {}
        for finding in all_findings:
            if finding.id not in unique_findings:
                unique_findings[finding.id] = finding
        
        result = AnalysisResult(
            project=project_name,
            timestamp=datetime.now().isoformat(),
            files_analyzed=files_analyzed,
            files_skipped=files_skipped,
            total_findings=len(unique_findings),
            findings=list(unique_findings.values()),
            token_usage={
                'input_tokens': total_input_tokens,
                'output_tokens': total_output_tokens,
                'total_tokens': total_input_tokens + total_output_tokens
            }
        )
        
        # Print summary
        self._print_summary(result)
        
        return result
    
    def _print_summary(self, result: AnalysisResult):
        """Print analysis summary."""
        console.print(f"\n[bold]Summary for {result.project}:[/bold]")
        console.print(f"  Files analyzed: {result.files_analyzed}")
        console.print(f"  Files skipped: {result.files_skipped}")
        console.print(f"  Total findings: {result.total_findings}")
        console.print(f"  Token usage: {result.token_usage['total_tokens']:,}")
        
        if result.findings:
            # Count by severity
            severity_counts = {}
            for finding in result.findings:
                sev = finding.severity
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
            
            console.print("  By severity:")
            for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
                if sev.value in severity_counts:
                    color = {
                        Severity.CRITICAL: 'red',
                        Severity.HIGH: 'orange1',
                        Severity.MEDIUM: 'yellow',
                        Severity.LOW: 'green'
                    }[sev]
                    console.print(f"    [{color}]{sev.value.capitalize()}:[/{color}] {severity_counts[sev.value]}")
    
    def save_result(self, result: AnalysisResult, output_dir: Path) -> Path:
        """Save analysis result to JSON file."""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"baseline_{result.project}.json"
        
        # Convert to dict for JSON serialization
        result_dict = asdict(result)
        result_dict['findings'] = [asdict(f) for f in result.findings]
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, indent=2)
        
        console.print(f"[green]Results saved to: {output_file}[/green]")
        return output_file


def main():
    parser = argparse.ArgumentParser(
        description='ScaBench Baseline Runner - Official baseline security analyzer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a single project
  %(prog)s --project my_project --source /path/to/source
  
  # Analyze with file limit
  %(prog)s --project my_project --source /path/to/source --max-files 20
  
  # Use specific model
  %(prog)s --project my_project --source /path/to/source --model gpt-4o
  
  # Custom output directory
  %(prog)s --project my_project --source /path/to/source --output results/
        """
    )
    
    parser.add_argument('--project', '-p', required=True,
                       help='Project name to analyze')
    parser.add_argument('--source', '-s', required=True,
                       help='Source directory containing project files')
    parser.add_argument('--output', '-o', default='baseline_results',
                       help='Output directory for results (default: baseline_results)')
    parser.add_argument('--max-files', type=int, metavar='N',
                       help='Maximum number of files to analyze')
    parser.add_argument('--model', '-m', default='gpt-5-mini',
                       help='OpenAI model to use (default: gpt-5-mini)')
    parser.add_argument('--patterns', nargs='+', metavar='PATTERN',
                       help='File patterns to analyze (e.g., "*.sol" "contracts/*.vy")')
    parser.add_argument('--api-key', help='OpenAI API key (or set OPENAI_API_KEY env var)')
    parser.add_argument('--config', '-c', help='Configuration file (JSON)')
    
    args = parser.parse_args()
    
    # Load configuration
    config = {}
    if args.config:
        with open(args.config, 'r') as f:
            config = json.load(f)
    
    # Override with command line arguments
    if args.model:
        config['model'] = args.model
    if args.api_key:
        config['api_key'] = args.api_key
    
    # Print header
    console.print(Panel.fit(
        "[bold cyan]SCABENCH BASELINE RUNNER[/bold cyan]\n"
        f"[dim]Model: {config.get('model', 'gpt-5-mini')}[/dim]",
        border_style="cyan"
    ))
    
    try:
        # Initialize runner
        runner = BaselineRunner(config)
        
        # Run analysis
        source_dir = Path(args.source)
        if not source_dir.exists():
            console.print(f"[red]Error: Source directory not found: {source_dir}[/red]")
            sys.exit(1)
        
        result = runner.analyze_project(
            project_name=args.project,
            source_dir=source_dir,
            max_files=args.max_files,
            file_patterns=args.patterns
        )
        
        # Save results
        output_dir = Path(args.output)
        output_file = runner.save_result(result, output_dir)
        
        # Final summary
        console.print("\n" + "="*60)
        console.print(Panel(
            f"[bold green]ANALYSIS COMPLETE[/bold green]\n\n"
            f"Project: {result.project}\n"
            f"Files analyzed: {result.files_analyzed}\n"
            f"Total findings: {result.total_findings}\n"
            f"Results saved to: {output_file}",
            border_style="green"
        ))
        
    except ValueError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()