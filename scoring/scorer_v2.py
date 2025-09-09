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
import re
import math
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

# LLM for intelligent matching
import llm

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
    undecided_findings: List[Dict[str, Any]]
    extra_findings: List[Dict[str, Any]]
    potential_matches: List[Dict[str, Any]]


class ScaBenchScorerV2:
    """Improved scorer with one-by-one matching for consistency."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the scorer with optional configuration."""
        self.config = config or {}
        # Use gpt-4o for best accuracy
        self.model_id = self.config.get('model', 'gpt-4o')
        self.api_key = self.config.get('api_key') or os.getenv("OPENAI_API_KEY")
        self.confidence_threshold = self.config.get('confidence_threshold', 0.75)
        # Strict matching mode: no confidence ratings, only exact matches count
        self.strict_matching = bool(self.config.get('strict_matching', False))
        
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
            
        self.debug = self.config.get('debug', False)
        self.verbose = self.config.get('verbose', False)
        # Chunked prompting + prefilter controls
        self.chunk_size = int(self.config.get('chunk_size', 10))
        self.enable_prefilter = bool(self.config.get('prefilter', True))
        # If >0, limit to the top-N most similar candidates before chunking
        self.prefilter_limit = int(self.config.get('prefilter_limit', 0))
        # Truncate long descriptions to keep prompts compact
        self.desc_max_chars = int(self.config.get('desc_max_chars', 800))

    # --------------------------
    # Similarity + hint helpers
    # --------------------------
    def _tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        # Lowercase and split on non-alphanumeric, keep tokens of len>=2
        tokens = re.split(r"[^A-Za-z0-9_]+", text.lower())
        return [t for t in tokens if len(t) >= 2]

    def _extract_hints(self, text: str) -> Tuple[set, set]:
        """Return (filenames, function_names) heuristically extracted from text."""
        if not text:
            return set(), set()
        filenames = set(re.findall(r"[A-Za-z0-9_./-]+\.sol\b", text))
        func_candidates = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", text))
        # Filter out common non-function keywords
        stop = {
            'if', 'for', 'while', 'require', 'assert', 'revert', 'emit', 'return', 'new',
            'mapping', 'event', 'modifier', 'function', 'constructor'
        }
        functions = {f for f in func_candidates if f.lower() not in stop}
        return filenames, functions

    def _truncate(self, text: str) -> str:
        if not text:
            return ''
        if len(text) <= self.desc_max_chars:
            return text
        return text[: self.desc_max_chars] + "..."

    def _similarity_score(self, expected: Dict[str, Any], candidate: Dict[str, Any]) -> float:
        """Lightweight lexical/hint-based similarity for prefiltering."""
        exp_text = (expected.get('title', '') or '') + "\n" + (expected.get('description', '') or '')
        cand_text = (candidate.get('title', '') or '') + "\n" + (candidate.get('description', '') or '')

        exp_tok = set(self._tokenize(exp_text))
        cand_tok = set(self._tokenize(cand_text))
        inter = len(exp_tok & cand_tok)
        denom = math.sqrt(max(len(exp_tok), 1) * max(len(cand_tok), 1))
        lexical = inter / denom if denom else 0.0

        exp_files, exp_funcs = self._extract_hints(exp_text)
        cand_files, cand_funcs = self._extract_hints(cand_text)
        file_bonus = 0.5 if exp_files and (exp_files & cand_files) else 0.0
        func_bonus = 0.3 if exp_funcs and (exp_funcs & cand_funcs) else 0.0

        sev_bonus = 0.1 if (expected.get('severity') and candidate.get('severity') and str(expected.get('severity')).lower() == str(candidate.get('severity')).lower()) else 0.0
        type_bonus = 0.1 if (expected.get('type') and candidate.get('type') and str(expected.get('type')).lower() == str(candidate.get('type')).lower()) else 0.0

        return lexical + file_bonus + func_bonus + sev_bonus + type_bonus

    def _build_findings_block(self, findings: List[Dict[str, Any]]) -> str:
        block = ""
        for idx, finding in enumerate(findings):
            file_hints, func_hints = self._extract_hints((finding.get('title', '') or '') + "\n" + (finding.get('description', '') or ''))
            file_line = f"\nFileHints: {', '.join(sorted(file_hints))}" if file_hints else ""
            func_line = f"\nFunctionHints: {', '.join(sorted(func_hints))}" if func_hints else ""
            block += f"""\n[FINDING {idx}]
Title: {finding.get('title', 'N/A')}
Severity: {finding.get('severity', 'N/A')}
Type: {finding.get('type', 'N/A')}{file_line}{func_line}
Description: {self._truncate(finding.get('description', 'N/A'))}
"""
        return block
    
    def find_match_in_results(self, expected: Dict, tool_findings: List[Dict]) -> Tuple[bool, Optional[Dict], str, float, str]:
        """
        Check if an expected vulnerability exists in the tool findings.
        Returns: (found_match, matched_finding, justification, confidence, decision)
        """

        def _prompt_with_fallback(prompt: str, system: str, schema: Dict[str, Any]):
            """Call model.prompt avoiding unsupported params; no temperature is set."""
            last_err: Optional[Exception] = None
            # Prefer determinism via seed if supported
            try:
                return self.model.prompt(
                    prompt,
                    system=system,
                    key=self.api_key,
                    schema=schema,
                    seed=42,
                    stream=False,
                )
            except Exception as e1:
                last_err = e1
                # Retry without seed
                try:
                    return self.model.prompt(
                        prompt,
                        system=system,
                        key=self.api_key,
                        schema=schema,
                        stream=False,
                    )
                except Exception as e2:
                    last_err = e2
                    raise last_err
        
        # Build prefilter ranking (optional) to focus the model
        indices = list(range(len(tool_findings)))
        if self.enable_prefilter and tool_findings:
            indices.sort(key=lambda i: self._similarity_score(expected, tool_findings[i]), reverse=True)
            if self.prefilter_limit and self.prefilter_limit > 0:
                indices = indices[: self.prefilter_limit]

        # Prepare expected hints to guide the model
        exp_text_all = (expected.get('title', 'N/A') or '') + "\n" + (expected.get('description', 'N/A') or '')
        exp_files, exp_funcs = self._extract_hints(exp_text_all)
        hints_block = ""
        if exp_files or exp_funcs:
            files_line = f"\nFilenameHints: {', '.join(sorted(exp_files))}" if exp_files else ""
            funcs_line = f"\nFunctionHints: {', '.join(sorted(exp_funcs))}" if exp_funcs else ""
            hints_block = files_line + funcs_line

        best_conf = -1.0
        best_global_idx: Optional[int] = None
        best_reason = ''
        undecided_reason = ''

        # Iterate in chunks
        for start in range(0, len(indices), max(self.chunk_size, 1)):
            chunk_idx = indices[start: start + max(self.chunk_size, 1)]
            chunk_findings = [tool_findings[i] for i in chunk_idx]

            findings_text = self._build_findings_block(chunk_findings)
            if self.strict_matching:
                prompt = f"""You are a security expert tasked with deciding if a specific vulnerability was detected.

EXPECTED VULNERABILITY:
Title: {expected.get('title', 'N/A')}
Description: {self._truncate(expected.get('description', 'N/A'))}
Severity: {expected.get('severity', 'N/A')}
Type: {expected.get('type', 'N/A')}{hints_block}

TOOL FINDINGS:
{findings_text}

## Strict True Positive Criteria (ALL must be clearly satisfied):
- Correct contract/location is identified (names or unique identifiers match).
- Correct function/entrypoint is identified when applicable.
- Core vulnerability mechanism/cause matches exactly.
- Consequences/impact align with the expected issue (allow minor phrasing differences only).

Important: If any element is uncertain or ambiguous, choose "undecided". Do not guess.

Respond with a JSON object using this schema (no confidence score):
{{
  "decision": "match" | "undecided" | "no",
  "matching_index": null or index of the matching finding,
  "reason": "brief explanation"
}}

If you choose "match", provide the BEST matching index. Only choose "match" if you are 100% confident that all strict criteria are met."""
                response_schema = {
                    "type": "object",
                    "properties": {
                        "decision": {"type": "string", "enum": ["match", "undecided", "no"]},
                        "matching_index": {"type": ["integer", "null"]},
                        "reason": {"type": "string"}
                    },
                    "required": ["decision", "matching_index", "reason"]
                }
            else:
                prompt = f"""You are a security expert tasked with finding if a specific vulnerability was detected.

EXPECTED VULNERABILITY:
Title: {expected.get('title', 'N/A')}
Description: {self._truncate(expected.get('description', 'N/A'))}
Severity: {expected.get('severity', 'N/A')}
Type: {expected.get('type', 'N/A')}{hints_block}

TOOL FINDINGS:
{findings_text}

## **Evaluation Criteria For True Positive:**
- **Correctly identifies the contract** where the issue exists.
- **Correctly identifies the function** where the issue occurs.
- **Accurately describes the core security issue** (even if phrased differently).
- **Accurately describes the potential consequences** (some variance allowed here as long as description is valid)

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
                response_schema = {
                    "type": "object",
                    "properties": {
                        "found": {"type": "boolean"},
                        "matching_index": {"type": ["integer", "null"]},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "reason": {"type": "string"}
                    },
                    "required": ["found", "matching_index", "confidence", "reason"]
                }

            try:
                response = _prompt_with_fallback(
                    prompt,
                    system="You are a precise vulnerability matcher. Be strict.",
                    schema=response_schema,
                )

                # Parse response
                if hasattr(response, 'text'):
                    result_text = response.text()
                elif hasattr(response, 'content'):
                    result_text = response.content
                else:
                    result_text = str(response)

                result = json.loads(result_text)

                if self.strict_matching:
                    decision = str(result.get('decision', 'no')).lower()
                    match_idx_local = result.get('matching_index')
                    if self.verbose:
                        console.print(
                            f"[yellow]LLM Response:[/yellow] decision={decision}, index={result.get('matching_index')}, "
                            f"chunk=({start}-{start+len(chunk_idx)-1}), reason={result.get('reason', 'N/A')[:100]}"
                        )
                    if decision == 'match' and match_idx_local is not None and 0 <= match_idx_local < len(chunk_idx):
                        global_idx = chunk_idx[match_idx_local]
                        return True, tool_findings[global_idx], result.get('reason', 'No reason provided'), 1.0, 'match'
                    elif decision == 'undecided':
                        if not undecided_reason:
                            undecided_reason = result.get('reason', 'Undecided')
                        # continue scanning other chunks
                        continue
                    else:
                        # explicit 'no' -> continue scanning
                        continue
                else:
                    if self.verbose:
                        console.print(
                            f"[yellow]LLM Response:[/yellow] found={result.get('found')}, "
                            f"confidence={result.get('confidence', 0):.2f}, index={result.get('matching_index')}, "
                            f"chunk=({start}-{start+len(chunk_idx)-1}), reason={result.get('reason', 'N/A')[:100]}"
                        )

                    confidence = float(result.get('confidence', 0) or 0.0)
                    match_idx_local = result.get('matching_index')

                    # Update best candidate even if below threshold
                    if result.get('found') and match_idx_local is not None and 0 <= match_idx_local < len(chunk_idx):
                        global_idx = chunk_idx[match_idx_local]
                        if confidence > best_conf:
                            best_conf = confidence
                            best_global_idx = global_idx
                            best_reason = result.get('reason', '')

                    # Return early if confident enough
                    if result.get('found', False) and confidence >= self.confidence_threshold:
                        if match_idx_local is not None and 0 <= match_idx_local < len(chunk_idx):
                            global_idx = chunk_idx[match_idx_local]
                            return True, tool_findings[global_idx], result.get('reason', 'No reason provided'), confidence, 'match'

            except Exception as e:
                if self.debug:
                    console.print(f"[red]Error matching: {e}[/red]")
                # Continue to next chunk, but remember error as reason if nothing else
                if not best_reason:
                    best_reason = f"Error: {str(e)}"

        # No chunk produced a positive match
        if self.strict_matching:
            if undecided_reason:
                return False, None, undecided_reason, 0.0, 'undecided'
            return False, None, "Not found (strict mode)", 0.0, 'no'
        else:
            # No chunk produced a match above threshold
            if best_global_idx is not None and 0 <= best_global_idx < len(tool_findings):
                return False, None, f"Closest candidate index={best_global_idx} (title='{tool_findings[best_global_idx].get('title','Unknown')[:80]}') with confidence={best_conf:.2f}.", float(max(best_conf, 0.0)), 'no'
            # If we encountered errors but no candidate to suggest, surface the error
            if best_reason:
                return False, None, best_reason, 0.0, 'no'
            return False, None, "Not found", 0.0, 'no'
    
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
        undecided_findings = []
        extra_findings = tool_findings.copy()  # Start with all as extra
        matched_tool_indices = set()
        
        # Progress bar for matching (only if not verbose)
        if self.verbose:
            # No progress bar in verbose mode to avoid flickering
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
                    
                    is_match, matched_finding, reason, confidence, decision = self.find_match_in_results(
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
                        target_list = missed_findings
                        label = 'Missed'
                        if self.strict_matching and decision == 'undecided':
                            target_list = undecided_findings
                            label = 'Undecided'
                        # Create the record
                        undecided_record = {
                            'id': f"{project_name}_expected_{exp_idx:03d}",
                            'title': expected.get('title', 'Unknown'),
                            'description': expected.get('description', ''),
                            'severity': expected.get('severity', 'unknown'),
                            'reason': reason or ('Undecided' if (self.strict_matching and decision == 'undecided') else 'Not detected by tool')
                        }
                        target_list.append(undecided_record)
                        
                        if self.debug or self.verbose:
                            console.print(f"[red]✗ {label}[/red] (confidence={confidence:.2f}): {expected.get('title', 'Unknown')[:60]}")
                else:
                    # No unmatched findings left to check
                    missed_findings.append({
                        'id': f"{project_name}_expected_{exp_idx:03d}",
                        'title': expected.get('title', 'Unknown'),
                        'description': expected.get('description', ''),
                        'severity': expected.get('severity', 'unknown'),
                        'reason': 'No unmatched tool findings remaining'
                    })
        else:
            # Use progress bar when not in verbose mode
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
                        is_match, matched_finding, reason, confidence, decision = self.find_match_in_results(
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
                                
                                if self.debug:
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
                            target_list = missed_findings if not (self.strict_matching and decision == 'undecided') else undecided_findings
                            target_list.append({
                                'id': f"{project_name}_expected_{exp_idx:03d}",
                                'title': expected.get('title', 'Unknown'),
                                'description': expected.get('description', ''),
                                'severity': expected.get('severity', 'unknown'),
                                'reason': reason or ('Undecided' if (self.strict_matching and decision == 'undecided') else 'Not detected by tool')
                            })
                            
                            if self.debug:
                                tag = 'Undecided' if (self.strict_matching and decision == 'undecided') else 'Missed'
                                console.print(f"[red]✗ {tag}[/red] (confidence={confidence:.2f}): {expected.get('title', 'Unknown')[:60]}")
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
        
        # Calculate metrics (undecided are treated as not matched for metrics)
        true_positives = len(matched_findings)
        false_negatives = len(missed_findings) + len(undecided_findings)
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
        if self.strict_matching and undecided_findings:
            table.add_row("Undecided (info)", str(len(undecided_findings)))
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
            undecided_findings=undecided_findings,
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
    parser.add_argument('--model', default='gpt-4o', help='LLM model to use')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--confidence-threshold', type=float, default=0.75, help='Confidence threshold for matches (default: 0.75)')
    parser.add_argument('--chunk-size', type=int, default=10, help='Max candidates per prompt chunk (default: 10)')
    parser.add_argument('--desc-max-chars', type=int, default=800, help='Max characters per description (default: 800)')
    parser.add_argument('--prefilter-limit', type=int, default=0, help='If >0, limit to top-N similar candidates before chunking')
    parser.add_argument('--no-prefilter', action='store_true', help='Disable lexical/hint prefiltering')
    parser.add_argument('--strict-matching', action='store_true', help='Enable strict matching (no confidence; undecided when in doubt)')
    
    args = parser.parse_args()

    # Always show which model is being used for clarity
    console.print(f"[cyan]Scorer model:[/cyan] {args.model}")

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
        'confidence_threshold': args.confidence_threshold,
        'chunk_size': args.chunk_size,
        'desc_max_chars': args.desc_max_chars,
        'prefilter_limit': args.prefilter_limit,
        'prefilter': not args.no_prefilter,
        'strict_matching': args.strict_matching,
    }
    scorer = ScaBenchScorerV2(config)
    
    if args.verbose:
        console.print(f"[cyan]Using confidence threshold: {args.confidence_threshold} | chunk-size={args.chunk_size} | prefilter={'on' if not args.no_prefilter else 'off'} | strict={'on' if args.strict_matching else 'off'}[/cyan]")
    
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
