#!/usr/bin/env python3
"""
Compare baseline results with expected vulnerabilities from the dataset.
Provides metrics for evaluating the baseline performance.
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass
import re
from collections import defaultdict


@dataclass
class ComparisonMetrics:
    """Metrics for comparing baseline findings with expected vulnerabilities"""
    project_id: str
    project_name: str
    
    # Counts
    baseline_findings: int
    expected_vulnerabilities: int
    
    # Severity breakdown
    baseline_by_severity: Dict[str, int]
    expected_by_severity: Dict[str, int]
    
    # Matching analysis
    potential_matches: List[Tuple[dict, dict, float]]  # (baseline, expected, similarity)
    
    def to_dict(self):
        return {
            'project_id': self.project_id,
            'project_name': self.project_name,
            'baseline_findings': self.baseline_findings,
            'expected_vulnerabilities': self.expected_vulnerabilities,
            'baseline_by_severity': self.baseline_by_severity,
            'expected_by_severity': self.expected_by_severity,
            'match_count': len(self.potential_matches),
            'precision': self.calculate_precision(),
            'recall': self.calculate_recall(),
            'f1_score': self.calculate_f1()
        }
    
    def calculate_precision(self) -> float:
        """Precision: matched findings / total baseline findings"""
        if self.baseline_findings == 0:
            return 0.0
        return len(self.potential_matches) / self.baseline_findings
    
    def calculate_recall(self) -> float:
        """Recall: matched findings / total expected vulnerabilities"""
        if self.expected_vulnerabilities == 0:
            return 0.0
        return len(self.potential_matches) / self.expected_vulnerabilities
    
    def calculate_f1(self) -> float:
        """F1 Score: harmonic mean of precision and recall"""
        precision = self.calculate_precision()
        recall = self.calculate_recall()
        if precision + recall == 0:
            return 0.0
        return 2 * (precision * recall) / (precision + recall)


class ResultsComparator:
    """Compare baseline results with expected vulnerabilities"""
    
    def __init__(self, baseline_dir: Path, dataset_path: Path):
        self.baseline_dir = Path(baseline_dir)
        self.dataset_path = Path(dataset_path)
        
        # Load dataset
        with open(self.dataset_path, 'r') as f:
            self.dataset = json.load(f)
        
        # Create project lookup
        self.projects_by_id = {
            p['project_id']: p for p in self.dataset['projects']
        }
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        # Convert to lowercase
        text = text.lower()
        # Remove special characters and extra whitespace
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using word overlap"""
        words1 = set(self.normalize_text(text1).split())
        words2 = set(self.normalize_text(text2).split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def find_matches(self, baseline_findings: List[dict], expected_vulns: List[dict]) -> List[Tuple[dict, dict, float]]:
        """Find potential matches between baseline and expected vulnerabilities"""
        matches = []
        matched_expected = set()
        
        for baseline in baseline_findings:
            best_match = None
            best_score = 0.0
            
            for i, expected in enumerate(expected_vulns):
                if i in matched_expected:
                    continue
                
                # Compare severities (must be compatible)
                if not self.severities_match(baseline['severity'], expected['severity']):
                    continue
                
                # Calculate similarity based on title and description
                title_sim = self.calculate_similarity(
                    baseline.get('title', ''),
                    expected.get('title', '')
                )
                
                desc_sim = self.calculate_similarity(
                    baseline.get('description', ''),
                    expected.get('description', '')
                )
                
                # Weighted average (title is more important)
                similarity = 0.7 * title_sim + 0.3 * desc_sim
                
                if similarity > best_score and similarity > 0.3:  # Threshold
                    best_match = (expected, i)
                    best_score = similarity
            
            if best_match:
                matches.append((baseline, best_match[0], best_score))
                matched_expected.add(best_match[1])
        
        return matches
    
    def severities_match(self, baseline_sev: str, expected_sev: str) -> bool:
        """Check if severities are compatible"""
        baseline_sev = baseline_sev.lower()
        expected_sev = expected_sev.lower()
        
        # Direct match
        if baseline_sev == expected_sev:
            return True
        
        # Allow some flexibility (e.g., high/critical, low/informational)
        severity_groups = [
            {'critical', 'high'},
            {'medium'},
            {'low', 'informational', 'info'}
        ]
        
        for group in severity_groups:
            if baseline_sev in group and expected_sev in group:
                return True
        
        return False
    
    def compare_project(self, project_id: str) -> ComparisonMetrics:
        """Compare baseline results with expected for a single project"""
        
        # Load baseline results
        baseline_file = self.baseline_dir / f"{project_id}_baseline.json"
        if not baseline_file.exists():
            raise FileNotFoundError(f"Baseline results not found: {baseline_file}")
        
        with open(baseline_file, 'r') as f:
            baseline_data = json.load(f)
        
        # Get expected vulnerabilities from dataset
        project = self.projects_by_id.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found in dataset")
        
        expected_vulns = project.get('vulnerabilities', [])
        baseline_findings = baseline_data.get('findings', [])
        
        # Count by severity
        baseline_by_severity = defaultdict(int)
        for finding in baseline_findings:
            baseline_by_severity[finding['severity'].lower()] += 1
        
        expected_by_severity = defaultdict(int)
        for vuln in expected_vulns:
            expected_by_severity[vuln['severity'].lower()] += 1
        
        # Find matches
        matches = self.find_matches(baseline_findings, expected_vulns)
        
        return ComparisonMetrics(
            project_id=project_id,
            project_name=project['name'],
            baseline_findings=len(baseline_findings),
            expected_vulnerabilities=len(expected_vulns),
            baseline_by_severity=dict(baseline_by_severity),
            expected_by_severity=dict(expected_by_severity),
            potential_matches=matches
        )
    
    def compare_all(self) -> Dict[str, ComparisonMetrics]:
        """Compare all projects that have baseline results"""
        results = {}
        
        # Find all baseline result files
        baseline_files = list(self.baseline_dir.glob("*_baseline.json"))
        
        for baseline_file in baseline_files:
            # Extract project ID from filename
            project_id = baseline_file.stem.replace('_baseline', '')
            
            try:
                metrics = self.compare_project(project_id)
                results[project_id] = metrics
            except Exception as e:
                print(f"Error comparing {project_id}: {e}")
        
        return results
    
    def generate_report(self, output_file: Path = None):
        """Generate a comparison report"""
        results = self.compare_all()
        
        if not results:
            print("No baseline results found to compare")
            return
        
        # Calculate aggregate metrics
        total_baseline = sum(m.baseline_findings for m in results.values())
        total_expected = sum(m.expected_vulnerabilities for m in results.values())
        total_matches = sum(len(m.potential_matches) for m in results.values())
        
        avg_precision = sum(m.calculate_precision() for m in results.values()) / len(results)
        avg_recall = sum(m.calculate_recall() for m in results.values()) / len(results)
        avg_f1 = sum(m.calculate_f1() for m in results.values()) / len(results)
        
        # Generate report
        report = []
        report.append("=" * 80)
        report.append("BASELINE COMPARISON REPORT")
        report.append("=" * 80)
        report.append(f"\nProjects analyzed: {len(results)}")
        report.append(f"Total baseline findings: {total_baseline}")
        report.append(f"Total expected vulnerabilities: {total_expected}")
        report.append(f"Total potential matches: {total_matches}")
        report.append(f"\nAverage Precision: {avg_precision:.2%}")
        report.append(f"Average Recall: {avg_recall:.2%}")
        report.append(f"Average F1 Score: {avg_f1:.2%}")
        
        report.append("\n" + "-" * 80)
        report.append("PROJECT DETAILS")
        report.append("-" * 80)
        
        for project_id, metrics in sorted(results.items(), key=lambda x: x[1].calculate_f1(), reverse=True):
            report.append(f"\n{metrics.project_name} ({project_id})")
            report.append(f"  Baseline findings: {metrics.baseline_findings}")
            report.append(f"  Expected vulnerabilities: {metrics.expected_vulnerabilities}")
            report.append(f"  Potential matches: {len(metrics.potential_matches)}")
            report.append(f"  Precision: {metrics.calculate_precision():.2%}")
            report.append(f"  Recall: {metrics.calculate_recall():.2%}")
            report.append(f"  F1 Score: {metrics.calculate_f1():.2%}")
            
            if metrics.baseline_by_severity:
                report.append(f"  Baseline by severity: {dict(metrics.baseline_by_severity)}")
            if metrics.expected_by_severity:
                report.append(f"  Expected by severity: {dict(metrics.expected_by_severity)}")
            
            # Show matched vulnerabilities
            if metrics.potential_matches:
                report.append("  Matched vulnerabilities:")
                for baseline, expected, similarity in sorted(metrics.potential_matches, key=lambda x: x[2], reverse=True)[:3]:
                    report.append(f"    - [{baseline['severity']}] {baseline['title'][:50]}...")
                    report.append(f"      matched: {expected['title'][:50]}... (sim: {similarity:.2f})")
        
        report_text = "\n".join(report)
        
        # Print to console
        print(report_text)
        
        # Save to file if specified
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report_text)
            print(f"\nReport saved to: {output_file}")
        
        # Also save JSON metrics
        json_file = output_file.with_suffix('.json') if output_file else Path('comparison_metrics.json')
        metrics_dict = {
            'summary': {
                'projects_analyzed': len(results),
                'total_baseline_findings': total_baseline,
                'total_expected_vulnerabilities': total_expected,
                'total_matches': total_matches,
                'avg_precision': avg_precision,
                'avg_recall': avg_recall,
                'avg_f1': avg_f1
            },
            'projects': {
                project_id: metrics.to_dict() 
                for project_id, metrics in results.items()
            }
        }
        
        with open(json_file, 'w') as f:
            json.dump(metrics_dict, f, indent=2)
        print(f"Metrics saved to: {json_file}")


def main():
    parser = argparse.ArgumentParser(description='Compare baseline results with expected vulnerabilities')
    
    parser.add_argument(
        'baseline_dir',
        help='Directory containing baseline results'
    )
    
    parser.add_argument(
        'dataset',
        help='Path to the dataset JSON file'
    )
    
    parser.add_argument(
        '--output',
        help='Output file for the comparison report'
    )
    
    args = parser.parse_args()
    
    comparator = ResultsComparator(
        baseline_dir=args.baseline_dir,
        dataset_path=args.dataset
    )
    
    output_file = Path(args.output) if args.output else None
    comparator.generate_report(output_file)


if __name__ == '__main__':
    main()