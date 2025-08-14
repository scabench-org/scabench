#!/usr/bin/env python3
"""
Evaluate baseline results against expected vulnerabilities.
Simple scoring: found, missed, false positives.
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, asdict
import re
from datetime import datetime


@dataclass
class IssueMatch:
    """Represents a match between baseline and expected issue"""
    expected_id: str
    expected_title: str
    expected_severity: str
    baseline_title: str
    baseline_file: str
    similarity_score: float
    
    def to_dict(self):
        return asdict(self)


@dataclass
class EvaluationResult:
    """Results for a single project evaluation"""
    project_id: str
    project_name: str
    
    # Found issues (matched with expected)
    found_issues: List[IssueMatch]
    
    # Missed issues (expected but not found)
    missed_issues: List[dict]
    
    # False positives (baseline findings that don't match any expected)
    false_positives: List[dict]
    
    # Counts by severity
    expected_high: int
    expected_medium: int
    expected_low: int
    
    found_high: int
    found_medium: int
    found_low: int
    
    def get_score(self) -> float:
        """Calculate score as percentage of expected issues found"""
        total_expected = self.expected_high + self.expected_medium + self.expected_low
        if total_expected == 0:
            return 0.0
        total_found = self.found_high + self.found_medium + self.found_low
        return (total_found / total_expected) * 100
    
    def to_dict(self):
        return {
            'project_id': self.project_id,
            'project_name': self.project_name,
            'score': f"{self.get_score():.1f}%",
            'summary': {
                'found': len(self.found_issues),
                'missed': len(self.missed_issues),
                'false_positives': len(self.false_positives)
            },
            'by_severity': {
                'high': f"{self.found_high}/{self.expected_high}",
                'medium': f"{self.found_medium}/{self.expected_medium}",
                'low': f"{self.found_low}/{self.expected_low}"
            },
            'found_issues': [m.to_dict() for m in self.found_issues],
            'missed_issues': self.missed_issues,
            'false_positives': self.false_positives
        }


class BaselineEvaluator:
    """Evaluate baseline results against expected vulnerabilities"""
    
    def __init__(self, baseline_dir: Path, dataset_path: Path, output_dir: Path = None):
        self.baseline_dir = Path(baseline_dir)
        self.dataset_path = Path(dataset_path)
        self.output_dir = output_dir or self.baseline_dir / 'evaluation'
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load dataset
        with open(self.dataset_path, 'r') as f:
            self.dataset = json.load(f)
        
        # Create project lookup
        self.projects_by_id = {
            p['project_id']: p for p in self.dataset['projects']
        }
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        if not text:
            return ""
        text = text.lower()
        # Remove URLs and code blocks
        text = re.sub(r'https?://[^\s]+', '', text)
        text = re.sub(r'```[^`]*```', '', text)
        # Remove special characters
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts"""
        words1 = set(self.normalize_text(text1).split())
        words2 = set(self.normalize_text(text2).split())
        
        if not words1 or not words2:
            return 0.0
        
        # Check for key vulnerability terms
        vuln_keywords = {
            'reentrancy', 'overflow', 'underflow', 'access', 'control',
            'frontrun', 'dos', 'denial', 'service', 'decimal', 'precision',
            'whitelist', 'blacklist', 'transfer', 'approve', 'allowance',
            'ownership', 'permission', 'unauthorized', 'manipulation'
        }
        
        key_words1 = words1 & vuln_keywords
        key_words2 = words2 & vuln_keywords
        
        # If both have key vulnerability terms, boost similarity
        key_match_boost = 0.3 if (key_words1 & key_words2) else 0.0
        
        # Calculate Jaccard similarity
        intersection = words1 & words2
        union = words1 | words2
        jaccard = len(intersection) / len(union) if union else 0.0
        
        return min(1.0, jaccard + key_match_boost)
    
    def severity_matches(self, sev1: str, sev2: str) -> bool:
        """Check if two severities match (ignoring informational)"""
        sev1 = sev1.lower()
        sev2 = sev2.lower()
        
        # Skip informational
        if 'info' in sev1 or 'info' in sev2:
            return False
        
        # Direct match
        if sev1 == sev2:
            return True
        
        # Allow high/critical to match
        if {sev1, sev2} <= {'high', 'critical'}:
            return True
        
        return False
    
    def find_best_match(self, expected_issue: dict, baseline_findings: List[dict]) -> Optional[Tuple[dict, float]]:
        """Find the best matching baseline finding for an expected issue"""
        best_match = None
        best_score = 0.0
        
        expected_title = expected_issue.get('title', '')
        expected_desc = expected_issue.get('description', '')
        expected_sev = expected_issue.get('severity', '')
        
        # Skip informational issues
        if 'info' in expected_sev.lower():
            return None
        
        for baseline in baseline_findings:
            # Check severity compatibility
            if not self.severity_matches(baseline.get('severity', ''), expected_sev):
                continue
            
            # Calculate similarity
            title_sim = self.calculate_similarity(
                baseline.get('title', ''),
                expected_title
            )
            
            desc_sim = self.calculate_similarity(
                baseline.get('description', ''),
                expected_desc
            )
            
            # Weight title more heavily
            combined_score = 0.6 * title_sim + 0.4 * desc_sim
            
            # Require minimum threshold
            if combined_score > best_score and combined_score > 0.25:
                best_match = baseline
                best_score = combined_score
        
        return (best_match, best_score) if best_match else None
    
    def evaluate_project(self, project_id: str) -> EvaluationResult:
        """Evaluate baseline results for a single project"""
        
        # Load baseline results
        baseline_file = self.baseline_dir / f"{project_id}_baseline.json"
        if not baseline_file.exists():
            raise FileNotFoundError(f"Baseline results not found: {baseline_file}")
        
        with open(baseline_file, 'r') as f:
            baseline_data = json.load(f)
        
        # Get expected vulnerabilities
        project = self.projects_by_id.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found in dataset")
        
        baseline_findings = baseline_data.get('findings', [])
        expected_vulns = [
            v for v in project.get('vulnerabilities', [])
            if 'info' not in v.get('severity', '').lower()
        ]
        
        # Track matches
        found_issues = []
        missed_issues = []
        matched_baseline_indices = set()
        
        # Count expected by severity
        expected_counts = {'high': 0, 'medium': 0, 'low': 0}
        found_counts = {'high': 0, 'medium': 0, 'low': 0}
        
        for expected in expected_vulns:
            sev = expected.get('severity', '').lower()
            if sev in expected_counts:
                expected_counts[sev] += 1
            elif sev == 'critical':
                expected_counts['high'] += 1
            
            # Try to find a match
            match_result = self.find_best_match(expected, baseline_findings)
            
            if match_result:
                baseline, score = match_result
                baseline_idx = baseline_findings.index(baseline)
                matched_baseline_indices.add(baseline_idx)
                
                # Record the match
                issue_match = IssueMatch(
                    expected_id=expected.get('finding_id', ''),
                    expected_title=expected.get('title', ''),
                    expected_severity=expected.get('severity', ''),
                    baseline_title=baseline.get('title', ''),
                    baseline_file=baseline.get('file_path', ''),
                    similarity_score=score
                )
                found_issues.append(issue_match)
                
                # Update found counts
                if sev in found_counts:
                    found_counts[sev] += 1
                elif sev == 'critical':
                    found_counts['high'] += 1
            else:
                # Issue was missed
                missed_issues.append({
                    'finding_id': expected.get('finding_id', ''),
                    'severity': expected.get('severity', ''),
                    'title': expected.get('title', ''),
                    'description': expected.get('description', '')[:200] + '...'
                })
        
        # Identify false positives (unmatched baseline findings)
        false_positives = []
        for i, baseline in enumerate(baseline_findings):
            if i not in matched_baseline_indices:
                # Skip informational
                if 'info' not in baseline.get('severity', '').lower():
                    false_positives.append({
                        'severity': baseline.get('severity', ''),
                        'title': baseline.get('title', ''),
                        'file': baseline.get('file_path', ''),
                        'description': baseline.get('description', '')[:200] + '...'
                    })
        
        return EvaluationResult(
            project_id=project_id,
            project_name=project['name'],
            found_issues=found_issues,
            missed_issues=missed_issues,
            false_positives=false_positives,
            expected_high=expected_counts['high'],
            expected_medium=expected_counts['medium'],
            expected_low=expected_counts['low'],
            found_high=found_counts['high'],
            found_medium=found_counts['medium'],
            found_low=found_counts['low']
        )
    
    def evaluate_all(self) -> Dict[str, EvaluationResult]:
        """Evaluate all projects with baseline results"""
        results = {}
        
        # Find all baseline result files
        baseline_files = list(self.baseline_dir.glob("*_baseline.json"))
        
        for baseline_file in baseline_files:
            project_id = baseline_file.stem.replace('_baseline', '')
            
            try:
                result = self.evaluate_project(project_id)
                results[project_id] = result
                
                # Save individual project evaluation
                project_output = self.output_dir / f"{project_id}_evaluation.json"
                with open(project_output, 'w') as f:
                    json.dump(result.to_dict(), f, indent=2)
                
                print(f"✓ Evaluated {result.project_name}: {len(result.found_issues)} found, {len(result.missed_issues)} missed, {len(result.false_positives)} false positives")
                
            except Exception as e:
                print(f"✗ Error evaluating {project_id}: {e}")
        
        return results
    
    def generate_summary(self, results: Dict[str, EvaluationResult]):
        """Generate summary report"""
        
        # Calculate totals
        total_found = sum(len(r.found_issues) for r in results.values())
        total_missed = sum(len(r.missed_issues) for r in results.values())
        total_false_positives = sum(len(r.false_positives) for r in results.values())
        
        total_expected = sum(
            r.expected_high + r.expected_medium + r.expected_low 
            for r in results.values()
        )
        
        # Generate summary
        summary = {
            'timestamp': datetime.now().isoformat(),
            'projects_evaluated': len(results),
            'overall_metrics': {
                'total_found': total_found,
                'total_missed': total_missed,
                'total_false_positives': total_false_positives,
                'total_expected': total_expected,
                'overall_recall': f"{(total_found / total_expected * 100) if total_expected else 0:.1f}%"
            },
            'by_severity': {
                'high': {
                    'found': sum(r.found_high for r in results.values()),
                    'expected': sum(r.expected_high for r in results.values())
                },
                'medium': {
                    'found': sum(r.found_medium for r in results.values()),
                    'expected': sum(r.expected_medium for r in results.values())
                },
                'low': {
                    'found': sum(r.found_low for r in results.values()),
                    'expected': sum(r.expected_low for r in results.values())
                }
            },
            'projects': {
                pid: {
                    'name': r.project_name,
                    'score': f"{r.get_score():.1f}%",
                    'found': len(r.found_issues),
                    'missed': len(r.missed_issues),
                    'false_positives': len(r.false_positives)
                }
                for pid, r in results.items()
            }
        }
        
        # Save summary
        summary_file = self.output_dir / 'evaluation_summary.json'
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Print report
        print("\n" + "=" * 80)
        print("BASELINE EVALUATION SUMMARY")
        print("=" * 80)
        print(f"\nProjects Evaluated: {len(results)}")
        print(f"Overall Recall: {summary['overall_metrics']['overall_recall']}")
        print(f"\nTotal Found: {total_found}")
        print(f"Total Missed: {total_missed}")
        print(f"Total False Positives: {total_false_positives}")
        
        print("\nBy Severity:")
        for sev in ['high', 'medium', 'low']:
            found = summary['by_severity'][sev]['found']
            expected = summary['by_severity'][sev]['expected']
            pct = (found / expected * 100) if expected else 0
            print(f"  {sev.upper()}: {found}/{expected} ({pct:.1f}%)")
        
        print("\nProject Details:")
        for pid, result in sorted(results.items(), key=lambda x: x[1].get_score(), reverse=True):
            print(f"\n  {result.project_name}")
            print(f"    Score: {result.get_score():.1f}%")
            print(f"    Found: {len(result.found_issues)}")
            print(f"    Missed: {len(result.missed_issues)}")
            print(f"    False Positives: {len(result.false_positives)}")
        
        print(f"\n✅ Full evaluation results saved to: {self.output_dir}")
        print(f"   - Summary: evaluation_summary.json")
        print(f"   - Individual evaluations: *_evaluation.json")
        
        return summary


def main():
    parser = argparse.ArgumentParser(description='Evaluate baseline results')
    
    parser.add_argument(
        'baseline_dir',
        help='Directory containing baseline results'
    )
    
    parser.add_argument(
        'dataset',
        help='Path to the dataset JSON file'
    )
    
    parser.add_argument(
        '--output-dir',
        help='Directory for evaluation outputs (default: baseline_dir/evaluation)'
    )
    
    args = parser.parse_args()
    
    evaluator = BaselineEvaluator(
        baseline_dir=args.baseline_dir,
        dataset_path=args.dataset,
        output_dir=Path(args.output_dir) if args.output_dir else None
    )
    
    print("Starting baseline evaluation...")
    results = evaluator.evaluate_all()
    
    if results:
        evaluator.generate_summary(results)
    else:
        print("No baseline results found to evaluate")


if __name__ == '__main__':
    main()