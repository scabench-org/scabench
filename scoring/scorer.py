#!/usr/bin/env python3
"""
ScaBench Scorer
Official scoring tool for evaluating security analysis tools against ScaBench benchmarks.
Uses EXTREMELY STRICT matching criteria with LLM-based intelligent matching.
"""

import json
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

# Rich for console output
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich import box

# LLM for intelligent matching
import llm

console = Console()


# STRICT MATCHING POLICY
MATCHING_POLICY = """
STRICT MATCHING REQUIREMENTS:

1. IDENTICAL LOCATION - Affected location reported must be the same file/contract/function
2. SAME IDENTIFIERS - Same class/contract names, function names, variables
3. IDENTICAL ROOT CAUSE - Not just similar, must be THE SAME vulnerability
4. IDENTICAL ATTACK VECTOR - The reported attack SHOULD be identical, slight variation is allowed as long as the exact same root causd is exploited
5. SAME IMPACT - Impact SHOULD be the same, slight variation (i.e. underreporting or overreporting) is allowed
6. NO MATCH for similar patterns in different locations
7. NO MATCH for same bug type but different functions
8. WHEN IN DOUBT: DO NOT MATCH

Only assign confidence = 1.0 for PERFECT matches.
Assign confidence < 1.0 for potential matches requiring review.
"""


# JSON Schema for the expected LLM response
MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "expected_index": {"type": "integer"},
                    "expected_title": {"type": "string"},
                    "found_index": {"type": "integer"},
                    "found_title": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "justification": {"type": "string"},
                    "dismissal_reasons": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "expected_index", "expected_title", "found_index", 
                    "found_title", "confidence", "justification"
                ],
            },
        },
        "unmatched_found": {
            "type": "array",
            "items": {"type": "integer"},
        },
    },
    "required": ["matches", "unmatched_found"],
}


@dataclass
class MatchResult:
    """Result of matching a finding to expected vulnerability."""
    matched: bool
    confidence: float
    justification: str
    expected_title: str
    found_title: str
    dismissal_reasons: List[str] = None


@dataclass
class ScoringResult:
    """Complete scoring result for a project."""
    project: str
    timestamp: str
    total_expected: int
    total_found: int
    true_positives: int
    false_negatives: int
    false_positives: int
    detection_rate: float
    precision: float
    f1_score: float
    matched_findings: List[Dict[str, Any]]
    missed_findings: List[Dict[str, Any]]
    extra_findings: List[Dict[str, Any]]
    potential_matches: List[Dict[str, Any]]


class ScaBenchScorer:
    """Main scorer for ScaBench benchmarks."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the scorer with optional configuration."""
        self.config = config or {}
        self.model_id = self.config.get('model', 'gpt-4o-mini')
        self.api_key = self.config.get('api_key') or os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            # llm will fall back to other key mechanisms, so this is not a fatal error
            # We will pass the key to the prompt method if it exists.
            pass

        try:
            self.model = llm.get_model(self.model_id)
        except llm.UnknownModelError:
            console.print(f"[red]Error: Model '{self.model_id}' not found. Is the plugin installed?[/red]")
            raise
        except Exception as e:
            console.print(f"[red]Error initializing LLM model: {e}[/red]")
            raise
    
    def batch_match_findings_with_llm(self, expected_findings: List[Dict], tool_findings: List[Dict]) -> Dict[str, Any]:
        """Use LLM to batch match all findings in a single call."""
        
        prompt = f"""{MATCHING_POLICY}

EXPECTED VULNERABILITIES (from benchmark):
{json.dumps(expected_findings, indent=2)}

FOUND VULNERABILITIES (from tool):
{json.dumps(tool_findings, indent=2)}

TASK: Match each expected vulnerability with found vulnerabilities (if any match exists).

For EACH expected vulnerability, determine if there's a matching found vulnerability.
Apply the STRICT matching criteria - only confidence = 1.0 counts as a match.

Return a JSON object with:
{{
    "matches": [
        {{
            "expected_index": <index in expected list>,
            "expected_title": "<title>",
            "found_index": <index in found list or -1 if no match>,
            "found_title": "<title or 'None'>",
            "confidence": <0.0 to 1.0, ONLY 1.0 for perfect matches>,
            "justification": "<explanation>",
            "dismissal_reasons": ["<reasons if confidence < 1.0>"]
        }}
    ],
    "unmatched_found": [<indices of found vulnerabilities that don't match any expected>]
}}

REMEMBER:
- Only assign confidence = 1.0 for PERFECT matches
- Each expected can match at most one found vulnerability
- Each found can match at most one expected vulnerability
- When in doubt, DO NOT MATCH (confidence < 1.0)
"""

        system_prompt = "You are a security expert evaluating vulnerability matches with EXTREME strictness. Return ONLY valid JSON."
        
        try:
            response = self.model.prompt(
                prompt,
                system=system_prompt,
                key=self.api_key,
                schema=MATCH_SCHEMA
            )
            return json.loads(response.text())
        except Exception as e:
            console.print(f"[red]Error in batch LLM matching: {e}[/red]")
            # Return empty matches on error
            return {
                "matches": [
                    {
                        "expected_index": i,
                        "expected_title": exp.get('title', 'Unknown'),
                        "found_index": -1,
                        "found_title": "None",
                        "confidence": 0.0,
                        "justification": f"Error during matching: {e}",
                        "dismissal_reasons": ["matching_error"]
                    }
                    for i, exp in enumerate(expected_findings)
                ],
                "unmatched_found": list(range(len(tool_findings)))
            }
    
    def score_project(self, 
                     expected_findings: List[Dict],
                     tool_findings: List[Dict],
                     project_name: str = "Unknown") -> ScoringResult:
        """Score a project by comparing tool findings to expected vulnerabilities.
        
        Args:
            expected_findings: List of expected vulnerabilities from benchmark
            tool_findings: List of vulnerabilities found by the tool
            project_name: Name of the project being scored
            
        Returns:
            ScoringResult with detailed matching information
        """
        console.print(f"\n[bold cyan]Scoring project: {project_name}[/bold cyan]")
        console.print(f"Expected: {len(expected_findings)}, Found: {len(tool_findings)}")
        
        matched_findings = []
        potential_matches = []
        missed_findings = []
        extra_findings = []
        
        # Use batch matching for efficiency - single LLM call instead of N×M
        console.print(f"[dim]Sending {len(expected_findings)} expected and {len(tool_findings)} found findings to LLM for batch matching...[/dim]")
        
        with console.status(f"[bold cyan]Matching findings for {project_name} with LLM (single batch call)...[/bold cyan]"):
            batch_result = self.batch_match_findings_with_llm(expected_findings, tool_findings)
        
        # Process batch results
        matched_indices = set()
        for match in batch_result.get('matches', []):
            expected_idx = match.get('expected_index', -1)
            found_idx = match.get('found_index', -1)
            confidence = match.get('confidence', 0.0)
            justification = match.get('justification', '')
            dismissal_reasons = match.get('dismissal_reasons', [])
            
            if expected_idx < 0 or expected_idx >= len(expected_findings):
                continue
                
            expected = expected_findings[expected_idx]
            found = tool_findings[found_idx] if 0 <= found_idx < len(tool_findings) else None
            
            if confidence == 1.0 and found:
                # Perfect match - count as true positive
                matched_findings.append({
                    # Titles for quick scanning
                    'expected': expected.get('title', 'Unknown'),
                    'matched': found.get('title', 'Unknown'),
                    'confidence': confidence,
                    'justification': justification,
                    'severity': expected.get('severity', 'unknown'),
                    # Full details for report
                    'expected_title': expected.get('title', 'Unknown'),
                    'expected_description': expected.get('description', ''),
                    'found_title': found.get('title', 'Unknown'),
                    'found_description': found.get('description', ''),
                    'found_id': found.get('id', '')
                })
                matched_indices.add(found_idx)
                
            elif confidence >= 0.5 and found:
                # Potential match - needs review, NOT counted as TP
                potential_matches.append({
                    # Titles for quick scanning
                    'expected': expected.get('title', 'Unknown'),
                    'matched': found.get('title', 'Unknown'),
                    'confidence': confidence,
                    'justification': justification,
                    'dismissal_reasons': dismissal_reasons,
                    'severity': expected.get('severity', 'unknown'),
                    # Full details for report
                    'expected_title': expected.get('title', 'Unknown'),
                    'expected_description': expected.get('description', ''),
                    'found_title': found.get('title', 'Unknown'),
                    'found_description': found.get('description', ''),
                    'found_id': found.get('id', '')
                })
                # Still counts as missed since confidence < 1.0
                missed_findings.append({
                    'title': expected.get('title', 'Unknown'),
                    'severity': expected.get('severity', 'unknown'),
                    'reason': f'Only potential match with confidence {confidence:.2f}'
                })
            else:
                # No match found
                missed_findings.append({
                    'title': expected.get('title', 'Unknown'),
                    'severity': expected.get('severity', 'unknown'),
                    'reason': 'No matching finding from tool'
                })
        
        # Identify extra findings (false positives)
        for idx, found in enumerate(tool_findings):
            if idx not in matched_indices:
                extra_findings.append(found)
        
        # Calculate metrics
        true_positives = len(matched_findings)  # Only confidence = 1.0
        false_negatives = len(missed_findings)
        false_positives = len(extra_findings)
        
        detection_rate = (true_positives / len(expected_findings)) if expected_findings else 0
        precision = (true_positives / len(tool_findings)) if tool_findings else 0
        f1_score = (2 * precision * detection_rate / (precision + detection_rate)) if (precision + detection_rate) > 0 else 0
        
        result = ScoringResult(
            project=project_name,
            timestamp=datetime.now().isoformat(),
            total_expected=len(expected_findings),
            total_found=len(tool_findings),
            true_positives=true_positives,
            false_negatives=false_negatives,
            false_positives=false_positives,
            detection_rate=detection_rate,
            precision=precision,
            f1_score=f1_score,
            matched_findings=matched_findings,
            missed_findings=missed_findings,
            extra_findings=[{'title': f.get('title', 'Unknown'), 
                           'severity': f.get('severity', 'unknown')} 
                          for f in extra_findings],
            potential_matches=potential_matches
        )
        
        # Print summary
        self._print_summary(result)
        
        return result
    
    def _print_summary(self, result: ScoringResult):
        """Print scoring summary."""
        console.print(f"\n[bold]Scoring Summary for {result.project}:[/bold]")
        console.print(f"  Expected vulnerabilities: {result.total_expected}")
        console.print(f"  Found by tool: {result.total_found}")
        console.print(f"  True positives (perfect matches): [green]{result.true_positives}[/green]")
        console.print(f"  False negatives (missed): [red]{result.false_negatives}[/red]")
        console.print(f"  False positives (extra): [yellow]{result.false_positives}[/yellow]")
        console.print(f"  Potential matches (need review): [cyan]{len(result.potential_matches)}[/cyan]")
        console.print(f"\n  Detection rate: {result.detection_rate:.1%}")
        console.print(f"  Precision: {result.precision:.1%}")
        console.print(f"  F1 Score: {result.f1_score:.1%}")
    
    def save_result(self, result: ScoringResult, output_dir: Path) -> Path:
        """Save scoring result to JSON file."""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"score_{result.project}.json"
        
        # Convert to dict for JSON serialization
        result_dict = asdict(result)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, indent=2)
        
        console.print(f"[green]Score saved to: {output_file}[/green]")
        return output_file


def load_benchmark_data(benchmark_file: Path, project_id: str = None) -> List[Dict]:
    """Load expected vulnerabilities from benchmark dataset.
    
    Args:
        benchmark_file: Path to benchmark JSON file
        project_id: Optional project ID to filter for
        
    Returns:
        List of expected vulnerabilities
    """
    with open(benchmark_file, 'r') as f:
        data = json.load(f)
    
    if project_id:
        # Find specific project
        for project in data:
            if project.get('project_id') == project_id or project.get('name') == project_id:
                return project.get('vulnerabilities', [])
        console.print(f"[yellow]Warning: Project {project_id} not found in benchmark[/yellow]")
        return []
    
    # Return all vulnerabilities (for batch processing)
    all_vulnerabilities = []
    for project in data:
        all_vulnerabilities.extend(project.get('vulnerabilities', []))
    return all_vulnerabilities


def load_tool_results(results_file: Path) -> List[Dict]:
    """Load tool analysis results.
    
    Args:
        results_file: Path to tool results JSON file
        
    Returns:
        List of found vulnerabilities
    """
    with open(results_file, 'r') as f:
        data = json.load(f)
    
    # Handle different result formats
    if isinstance(data, dict):
        if 'findings' in data:
            return data['findings']
        elif 'vulnerabilities' in data:
            return data['vulnerabilities']
    elif isinstance(data, list):
        # Could be list of findings or list of projects
        if data and isinstance(data[0], dict):
            if 'findings' in data[0]:
                # List of projects, extract all findings
                all_findings = []
                for project in data:
                    all_findings.extend(project.get('findings', []))
                return all_findings
            else:
                # Direct list of findings
                return data
    
    console.print(f"[yellow]Warning: No findings found in {results_file}[/yellow]")
    return []


def main():
    parser = argparse.ArgumentParser(
        description='ScaBench Scorer - Evaluate security tools with STRICT matching',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Score a single project
  %(prog)s --benchmark dataset.json --results baseline_results.json --project my_project
  
  # Score all projects in results directory
  %(prog)s --benchmark dataset.json --results-dir baseline_results/ --output scores/
  
  # Use different model for matching
  %(prog)s --benchmark dataset.json --results results.json --model gpt-4o
  
  # Show detailed matching justifications
  %(prog)s --benchmark dataset.json --results results.json --verbose
        """
    )
    
    parser.add_argument('--benchmark', '-b', required=True,
                       help='Path to benchmark dataset JSON file')
    parser.add_argument('--results', '-r',
                       help='Path to tool results JSON file')
    parser.add_argument('--results-dir', '-d',
                       help='Directory containing multiple result files')
    parser.add_argument('--project', '-p',
                       help='Specific project to score')
    parser.add_argument('--output', '-o', default='scoring_results',
                       help='Output directory for scores (default: scoring_results)')
    parser.add_argument('--model', '-m', default='gpt-4o-mini',
                       help='LLM model for matching (default: gpt-4o-mini)')
    parser.add_argument('--api-key', help='OpenAI API key (or set OPENAI_API_KEY env var)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed matching justifications')
    parser.add_argument('--config', '-c', help='Configuration file (JSON)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.results and not args.results_dir:
        parser.error("Either --results or --results-dir must be specified")
    
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
    
    # Print header with strict policy reminder
    console.print(Panel.fit(
        "[bold cyan]SCABENCH SCORER[/bold cyan]\n"
        f"[bold yellow]Model: {config.get('model', 'gpt-4o-mini')}[/bold yellow]\n\n"
        "[bold red]USING STRICT MATCHING CRITERIA[/bold red]\n"
        "[yellow]Only slight variations are allowed[/yellow]",
        border_style="cyan"
    ))
    
    # Show matching policy
    console.print(Panel(
        MATCHING_POLICY,
        title="[bold]Strict Matching Policy[/bold]",
        border_style="red"
    ))
    
    try:
        # Initialize scorer
        scorer = ScaBenchScorer(config)
        
        # Load benchmark data
        benchmark_path = Path(args.benchmark)
        if not benchmark_path.exists():
            console.print(f"[red]Error: Benchmark file not found: {benchmark_path}[/red]")
            sys.exit(1)
        
        # Process single file or directory
        if args.results:
            # Single file mode
            results_path = Path(args.results)
            if not results_path.exists():
                console.print(f"[red]Error: Results file not found: {results_path}[/red]")
                sys.exit(1)
            
            # Load data
            expected = load_benchmark_data(benchmark_path, args.project)
            found = load_tool_results(results_path)
            
            # Score
            project_name = args.project or results_path.stem
            result = scorer.score_project(expected, found, project_name)
            
            # Save result
            output_dir = Path(args.output)
            output_file = scorer.save_result(result, output_dir)
            
            # Show detailed justifications if verbose
            if args.verbose:
                if result.matched_findings:
                    console.print("\n[bold green]MATCHED FINDINGS (True Positives):[/bold green]")
                    for match in result.matched_findings:
                        console.print(Panel(
                            f"[cyan]Expected:[/cyan] {match['expected']}\n"
                            f"[green]Matched:[/green] {match['matched']}\n"
                            f"[yellow]Confidence:[/yellow] {match['confidence']:.2f}\n\n"
                            f"[dim]Justification:[/dim]\n{match['justification']}",
                            border_style="green"
                        ))
                
                if result.potential_matches:
                    console.print("\n[bold yellow]POTENTIAL MATCHES (Need Review):[/bold yellow]")
                    for match in result.potential_matches:
                        console.print(Panel(
                            f"[cyan]Expected:[/cyan] {match['expected']}\n"
                            f"[yellow]Matched:[/yellow] {match['matched']}\n"
                            f"[red]Confidence:[/red] {match['confidence']:.2f}\n"
                            f"[red]Dismissal:[/red] {', '.join(match.get('dismissal_reasons', []))}\n\n"
                            f"[dim]Justification:[/dim]\n{match['justification']}",
                            border_style="yellow"
                        ))
        
        else:
            # Directory mode
            results_dir = Path(args.results_dir)
            if not results_dir.exists():
                console.print(f"[red]Error: Results directory not found: {results_dir}[/red]")
                sys.exit(1)
            
            # Process all result files
            result_files = list(results_dir.glob("*.json"))
            console.print(f"\n[bold]Found {len(result_files)} result files to score[/bold]\n")
            
            all_scores = []
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task("Scoring projects...", total=len(result_files))
                
                for i, result_file in enumerate(result_files):
                    # Extract project name from filename
                    project_name = result_file.stem.replace('baseline_', '')
                    progress.update(task, description=f"[cyan]Scoring project {i+1}/{len(result_files)}: {project_name}[/cyan]")
                    
                    # Load data
                    expected = load_benchmark_data(benchmark_path, project_name)
                    if not expected:
                        console.print(f"[yellow]Skipping {project_name}: No benchmark data[/yellow]")
                        progress.advance(task)
                        continue
                    
                    found = load_tool_results(result_file)
                    
                    # Score
                    result = scorer.score_project(expected, found, project_name)
                    all_scores.append(result)
                    
                    # Save result
                    output_dir = Path(args.output)
                    scorer.save_result(result, output_dir)
                    
                    progress.advance(task)
            
            # Print overall summary
            if all_scores:
                console.print("\n" + "="*60)
                total_tp = sum(r.true_positives for r in all_scores)
                total_expected = sum(r.total_expected for r in all_scores)
                overall_detection = (total_tp / total_expected * 100) if total_expected > 0 else 0
                
                console.print(Panel(
                    f"[bold cyan]OVERALL RESULTS[/bold cyan]\n\n"
                    f"Projects scored: {len(all_scores)}\n"
                    f"Total expected vulnerabilities: {total_expected}\n"
                    f"Total true positives: [green]{total_tp}[/green]\n"
                    f"Overall detection rate: {overall_detection:.1f}%\n\n"
                    f"Results saved to: {args.output}/",
                    border_style="cyan"
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
