#!/usr/bin/env python3
"""
ScaBench Scorer V2 - One-by-One Matching
More deterministic scoring using individual finding comparisons.
Processes each expected finding sequentially for better consistency.
"""

import json
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict

# Rich for console output
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich import box

# OpenAI for LLM matching
from openai import OpenAI

console = Console()


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


class ScaBenchScorerV2:
    """Improved scorer with one-by-one matching for consistency."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the scorer with optional configuration."""
        self.config = config or {}
        # Use gpt-4o-mini for cost-effectiveness and good performance
        self.model = self.config.get('model', 'gpt-4o-mini')
        self.api_key = self.config.get('api_key') or os.getenv("OPENAI_API_KEY")
        self.confidence_threshold = self.config.get('confidence_threshold', 0.75)
        
        if not self.api_key:
            raise ValueError("OpenAI API key not provided. Set OPENAI_API_KEY environment variable.")
        
        self.client = OpenAI(api_key=self.api_key)
        self.debug = self.config.get('debug', False)
        self.verbose = self.config.get('verbose', False)
    
    def find_match_in_results(self, expected: Dict, tool_findings: List[Dict]) -> Tuple[bool, Optional[Dict], str]:
        """
        Check if an expected vulnerability exists in the tool findings.
        Returns: (found_match, matched_finding, justification)
        """
        
        # Format tool findings for the prompt
        findings_text = ""
        for idx, finding in enumerate(tool_findings):
            findings_text += f"""\n[FINDING {idx}]
Title: {finding.get('title', 'N/A')}
Description: {finding.get('description', 'N/A')}
Severity: {finding.get('severity', 'N/A')}
Type: {finding.get('type', 'N/A')}
"""
        
        prompt = f"""You are a security expert tasked with finding if a specific vulnerability was detected.

EXPECTED VULNERABILITY:
Title: {expected.get('title', 'N/A')}
Description: {expected.get('description', 'N/A')}
Severity: {expected.get('severity', 'N/A')}
Type: {expected.get('type', 'N/A')}

TOOL FINDINGS:
{findings_text}

STRICT MATCHING RULES:
1. Must be the SAME vulnerability, not just similar type
2. Must have the SAME location
3. Must have the SAME root cause
4. Must describe the SAME attack vector
5. Description of impact should be the same (slight variations allowed)

Answer with a JSON object:
{{
    "found": true/false,
    "matching_index": null or index of matching finding,
    "confidence": 0.0-1.0,
    "reason": "brief explanation"
}}

If found, provide the index of the BEST matching finding.
Return confidence between 0.0-1.0 based on match quality:
- 1.0 = Perfect match (same vulnerability, location, cause)
- 0.9 = Very strong match (minor wording differences)
- 0.8 = Strong match (same issue, slight variations)
- 0.7 = Good match (clearly the same vulnerability)
- 0.6 = Moderate match (likely same, some uncertainty)
- Below 0.5 = Poor match or different vulnerability

When in doubt, lean towards lower confidence."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a precise vulnerability matcher. Be strict."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0,  # Maximum determinism
                seed=42  # Fixed seed for consistency
            )
            
            result = json.loads(response.choices[0].message.content)
            
            if self.verbose:
                console.print(f"[yellow]LLM Response:[/yellow] found={result.get('found')}, "
                            f"confidence={result.get('confidence', 0):.2f}, "
                            f"index={result.get('matching_index')}, "
                            f"reason={result.get('reason', 'N/A')[:100]}")
            
            confidence = result.get('confidence', 0)
            if result.get('found', False) and confidence >= self.confidence_threshold:
                match_idx = result.get('matching_index')
                if match_idx is not None and 0 <= match_idx < len(tool_findings):
                    return True, tool_findings[match_idx], result.get('reason', 'No reason provided'), confidence
            
            return False, None, result.get('reason', 'Not found'), confidence
            
        except Exception as e:
            if self.debug:
                console.print(f"[red]Error matching: {e}[/red]")
            return False, None, f"Error: {str(e)}"
    
    def score_project(self, 
                     expected_findings: List[Dict],
                     tool_findings: List[Dict],
                     project_name: str = "Unknown") -> ScoringResult:
        """
        Score a project by comparing tool findings to expected vulnerabilities.
        Uses one-by-one matching for consistency.
        """
        console.print(Panel.fit(
            f"[bold cyan]Scoring Project: {project_name}[/bold cyan]\n"
            f"Expected: {len(expected_findings)} | Found: {len(tool_findings)}",
            border_style="cyan"
        ))
        
        matched_findings = []
        missed_findings = []
        extra_findings = tool_findings.copy()  # Start with all as extra
        matched_tool_indices = set()
        
        # Progress bar for matching
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            
            task = progress.add_task(
                f"Matching {len(expected_findings)} expected findings...", 
                total=len(expected_findings)
            )
            
            # For each expected finding, check if it exists in tool findings
            for exp_idx, expected in enumerate(expected_findings):
                # Get remaining unmatched tool findings
                unmatched_findings = [
                    (idx, finding) for idx, finding in enumerate(tool_findings)
                    if idx not in matched_tool_indices
                ]
                
                # Check if this expected finding matches any unmatched tool finding
                if unmatched_findings:
                    if self.verbose:
                        console.print(f"\n[cyan]Checking:[/cyan] {expected.get('title', 'Unknown')[:80]}...")
                    
                    is_match, matched_finding, reason, confidence = self.find_match_in_results(
                        expected, 
                        [f for _, f in unmatched_findings]
                    )
                    
                    if is_match and matched_finding:
                        # Find the original index of the matched finding
                        tool_idx = None
                        for orig_idx, (idx, finding) in enumerate(unmatched_findings):
                            if finding == matched_finding:
                                tool_idx = idx
                                break
                        
                        if tool_idx is not None:
                            # Record the match
                            matched_findings.append({
                                'id': f"{project_name}_expected_{exp_idx:03d}",
                                'expected': expected.get('title', 'Unknown'),
                                'matched': matched_finding.get('title', 'Unknown'),
                                'confidence': confidence,
                                'justification': reason,
                                'severity': expected.get('severity', 'unknown'),
                                'expected_description': expected.get('description', ''),
                                'found_description': matched_finding.get('description', ''),
                                'found_id': matched_finding.get('id', ''),
                                'tool_finding_index': tool_idx
                            })
                            matched_tool_indices.add(tool_idx)
                            
                            if self.debug or self.verbose:
                                console.print(f"[green]✓ Matched[/green] (confidence={confidence:.2f}): {expected.get('title', 'Unknown')[:60]}")
                        else:
                            # Shouldn't happen but handle gracefully
                            missed_findings.append({
                                'id': f"{project_name}_expected_{exp_idx:03d}",
                                'title': expected.get('title', 'Unknown'),
                                'description': expected.get('description', ''),
                                'severity': expected.get('severity', 'unknown'),
                                'reason': 'Match found but index lost'
                            })
                    else:
                        # No match found
                        missed_findings.append({
                            'id': f"{project_name}_expected_{exp_idx:03d}",
                            'title': expected.get('title', 'Unknown'),
                            'description': expected.get('description', ''),
                            'severity': expected.get('severity', 'unknown'),
                            'reason': reason or 'Not detected by tool'
                        })
                        
                        if self.debug or self.verbose:
                            console.print(f"[red]✗ Missed[/red] (confidence={confidence:.2f}): {expected.get('title', 'Unknown')[:60]}")
                else:
                    # No unmatched findings left to check
                    missed_findings.append({
                        'id': f"{project_name}_expected_{exp_idx:03d}",
                        'title': expected.get('title', 'Unknown'),
                        'description': expected.get('description', ''),
                        'severity': expected.get('severity', 'unknown'),
                        'reason': 'No unmatched tool findings remaining'
                    })
                
                progress.advance(task)
        
        # Identify extra findings (false positives)
        extra_findings = []
        for tool_idx, found in enumerate(tool_findings):
            if tool_idx not in matched_tool_indices:
                extra_findings.append({
                    'id': f"{project_name}_tool_{tool_idx:03d}",
                    'title': found.get('title', 'Unknown'),
                    'description': found.get('description', ''),
                    'severity': found.get('severity', 'unknown'),
                    'original_id': found.get('id', '')
                })
        
        # Calculate metrics
        true_positives = len(matched_findings)
        false_negatives = len(missed_findings)
        false_positives = len(extra_findings)
        
        detection_rate = (true_positives / len(expected_findings)) if expected_findings else 0.0
        precision = (true_positives / (true_positives + false_positives)) if (true_positives + false_positives) > 0 else 0.0
        f1_score = (2 * precision * detection_rate / (precision + detection_rate)) if (precision + detection_rate) > 0 else 0.0
        
        # Display results summary
        table = Table(title="Scoring Summary", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        
        table.add_row("True Positives", str(true_positives))
        table.add_row("False Negatives", str(false_negatives))
        table.add_row("False Positives", str(false_positives))
        table.add_row("Detection Rate", f"{detection_rate*100:.1f}%")
        table.add_row("Precision", f"{precision*100:.1f}%")
        table.add_row("F1 Score", f"{f1_score*100:.1f}%")
        
        console.print(table)
        
        return ScoringResult(
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
            extra_findings=extra_findings,
            potential_matches=[]  # Not used in V2
        )


def main():
    """Main entry point for standalone scoring."""
    parser = argparse.ArgumentParser(description='ScaBench Scorer V2 - One-by-one matching')
    parser.add_argument('--benchmark', required=True, help='Path to benchmark JSON file')
    parser.add_argument('--results-dir', required=True, help='Directory containing tool results')
    parser.add_argument('--output', default='scoring_results', help='Output directory')
    parser.add_argument('--project', help='Score only a specific project')
    parser.add_argument('--model', default='gpt-4o-mini', help='OpenAI model to use')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--confidence-threshold', type=float, default=0.75, help='Confidence threshold for matches (default: 0.75)')
    
    args = parser.parse_args()
    
    # Load benchmark data
    with open(args.benchmark, 'r') as f:
        benchmark = json.load(f)
    
    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize scorer
    config = {
        'model': args.model,
        'debug': args.debug,
        'verbose': args.verbose,
        'confidence_threshold': args.confidence_threshold
    }
    scorer = ScaBenchScorerV2(config)
    
    if args.verbose:
        console.print(f"[cyan]Using confidence threshold: {args.confidence_threshold}[/cyan]")
    
    # Find results files
    results_dir = Path(args.results_dir)
    results_files = list(results_dir.glob('*.json'))
    
    if not results_files:
        console.print(f"[red]No result files found in {results_dir}[/red]")
        sys.exit(1)
    
    console.print(f"Found {len(results_files)} result files to score")
    
    # Score each project
    for result_file in results_files:
        # Extract project ID from filename (remove "baseline_" prefix if present)
        project_id = result_file.stem
        if project_id.startswith('baseline_'):
            project_id = project_id[9:]  # Remove "baseline_" prefix
        
        if args.project and project_id != args.project:
            continue
        
        # Load tool results
        with open(result_file, 'r') as f:
            tool_results = json.load(f)
        
        # Get tool findings
        tool_findings = tool_results.get('findings', [])
        
        # Find corresponding benchmark entry
        expected_findings = []
        for entry in benchmark:
            if entry.get('project_id') == project_id or entry.get('id') == project_id:
                expected_findings = entry.get('vulnerabilities', [])
                break
        
        if not expected_findings:
            console.print(f"[yellow]No benchmark data for {project_id}, skipping[/yellow]")
            continue
        
        # Score the project
        result = scorer.score_project(expected_findings, tool_findings, project_id)
        
        # Save results
        output_file = output_dir / f"score_{project_id}.json"
        with open(output_file, 'w') as f:
            json.dump(asdict(result), f, indent=2)
        
        console.print(f"[green]✓ Saved results to {output_file}[/green]")
    
    console.print("\n[bold green]Scoring complete![/bold green]")


if __name__ == "__main__":
    main()