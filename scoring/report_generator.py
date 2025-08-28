#!/usr/bin/env python3
"""
ScaBench Report Generator
Generate comprehensive HTML reports from scoring results with visualizations.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import argparse
from collections import defaultdict
import base64
from io import BytesIO

# Rich for console output
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

# For visualization (optional)
try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    console.print("[yellow]Warning: matplotlib not installed. Charts will be disabled.[/yellow]")
    console.print("[dim]Install with: pip install matplotlib[/dim]")


class ReportGenerator:
    """Generate HTML reports from ScaBench scoring results."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the report generator."""
        self.config = config or {}
        self.scan_info = {
            'tool_name': self.config.get('tool_name', 'Baseline Analyzer'),
            'tool_version': self.config.get('tool_version', 'v1.0'),
            'model': self.config.get('model', 'Not specified'),
            'scan_date': self.config.get('scan_date', datetime.now().strftime('%Y-%m-%d')),
            'benchmark_version': self.config.get('benchmark_version', 'ScaBench v1.0'),
            'notes': self.config.get('notes', ''),
        }
    
    def _generate_chart_base64(self, data: Dict[str, Any], chart_type: str) -> str:
        """Generate a chart and return as base64 encoded string."""
        if not HAS_MATPLOTLIB:
            return ""
        
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            if chart_type == 'detection_by_project':
                projects = [r['project'][:20] for r in data['projects']]
                detection_rates = [r['detection_rate'] * 100 for r in data['projects']]
                
                ax.barh(projects, detection_rates, color='steelblue')
                ax.set_xlabel('Detection Rate (%)')
                ax.set_title('Detection Rate by Project')
                ax.set_xlim(0, 100)
                
            elif chart_type == 'severity_distribution':
                severities = ['Critical', 'High', 'Medium', 'Low']
                expected = []
                found = []
                
                for sev in ['critical', 'high', 'medium', 'low']:
                    exp_count = data['severity_stats'].get(sev, {}).get('expected', 0)
                    found_count = data['severity_stats'].get(sev, {}).get('found', 0)
                    expected.append(exp_count)
                    found.append(found_count)
                
                x = np.arange(len(severities))
                width = 0.35
                
                ax.bar(x - width/2, expected, width, label='Expected', color='lightcoral')
                ax.bar(x + width/2, found, width, label='Found', color='lightgreen')
                ax.set_xlabel('Severity')
                ax.set_ylabel('Count')
                ax.set_title('Vulnerabilities by Severity')
                ax.set_xticks(x)
                ax.set_xticklabels(severities)
                ax.legend()
            
            elif chart_type == 'overall_metrics':
                metrics = ['Detection Rate', 'Precision', 'F1 Score']
                values = [
                    data['overall_stats']['detection_rate'],
                    data['overall_stats']['precision'],
                    data['overall_stats']['f1_score']
                ]
                
                ax.bar(metrics, values, color=['green', 'blue', 'purple'])
                ax.set_ylabel('Percentage')
                ax.set_title('Overall Performance Metrics')
                ax.set_ylim(0, 100)
                
                # Add value labels on bars
                for i, v in enumerate(values):
                    ax.text(i, v + 1, f'{v:.1f}%', ha='center')
            
            # Convert to base64
            buffer = BytesIO()
            plt.tight_layout()
            plt.savefig(buffer, format='png', dpi=100)
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            plt.close()
            
            return f"data:image/png;base64,{image_base64}"
            
        except Exception as e:
            console.print(f"[yellow]Warning: Could not generate chart: {e}[/yellow]")
            return ""
    
    def _format_dismissal_reasons(self, reasons: List[str]) -> str:
        """Format dismissal reasons as HTML badges."""
        if not reasons:
            return ''
        
        reason_map = {
            'different_root_cause': 'Different Root Cause',
            'different_location': 'Wrong Location',
            'different_function': 'Wrong Function',
            'different_contract': 'Wrong Contract',
            'different_variable': 'Wrong Variables',
            'wrong_attack_vector': 'Wrong Attack Vector',
            'different_impact': 'Different Impact',
            'missing_identifiers': 'Missing Identifiers',
            'general_description': 'Too Vague',
            'not_found': 'Not Found',
            'matching_error': 'Matching Error'
        }
        
        badges_html = '<div class="dismissal-reasons">'
        for reason in reasons:
            label = reason_map.get(reason, reason)
            badges_html += f'<span class="dismissal-badge">{label}</span>'
        badges_html += '</div>'
        return badges_html
    
    def generate_report(self, 
                       scores_dir: Path,
                       benchmark_file: Optional[Path] = None,
                       output_file: Path = Path("report.html")) -> Path:
        """Generate HTML report from scoring results.
        
        Args:
            scores_dir: Directory containing score_*.json files
            benchmark_file: Optional path to benchmark dataset
            output_file: Output HTML file path
            
        Returns:
            Path to generated HTML report
        """
        console.print("[cyan]Generating ScaBench report...[/cyan]")
        
        # Load all scoring results
        score_files = list(scores_dir.glob("score_*.json"))
        if not score_files:
            console.print(f"[red]No score files found in {scores_dir}[/red]")
            sys.exit(1)
        
        all_scores = []
        for score_file in score_files:
            with open(score_file, 'r') as f:
                all_scores.append(json.load(f))
        
        # Calculate aggregate statistics
        total_expected = sum(s['total_expected'] for s in all_scores)
        total_found = sum(s['total_found'] for s in all_scores)
        total_tp = sum(s['true_positives'] for s in all_scores)
        total_fn = sum(s['false_negatives'] for s in all_scores)
        total_fp = sum(s['false_positives'] for s in all_scores)
        total_potential = sum(len(s.get('potential_matches', [])) for s in all_scores)
        
        overall_detection = (total_tp / total_expected * 100) if total_expected > 0 else 0
        overall_precision = (total_tp / total_found * 100) if total_found > 0 else 0
        overall_f1 = (2 * overall_precision * overall_detection / 
                     (overall_precision + overall_detection)) if (overall_precision + overall_detection) > 0 else 0
        
        # Severity statistics
        severity_stats = defaultdict(lambda: {'expected': 0, 'found': 0})
        for score in all_scores:
            for miss in score.get('missed_findings', []):
                severity = miss.get('severity', 'unknown')
                severity_stats[severity]['expected'] += 1
            for match in score.get('matched_findings', []):
                severity = match.get('severity', 'unknown')
                severity_stats[severity]['found'] += 1
                severity_stats[severity]['expected'] += 1
        
        # Prepare data for charts
        chart_data = {
            'projects': [{'project': s['project'], 
                         'detection_rate': s['detection_rate']} 
                        for s in all_scores],
            'severity_stats': dict(severity_stats),
            'overall_stats': {
                'detection_rate': overall_detection,
                'precision': overall_precision,
                'f1_score': overall_f1
            }
        }
        
        # Generate charts
        chart_detection = self._generate_chart_base64(chart_data, 'detection_by_project')
        chart_severity = self._generate_chart_base64(chart_data, 'severity_distribution')
        chart_metrics = self._generate_chart_base64(chart_data, 'overall_metrics')
        
        # Generate HTML
        html_content = self._generate_html(
            all_scores,
            {
                'total_projects': len(all_scores),
                'total_expected': total_expected,
                'total_found': total_found,
                'total_tp': total_tp,
                'total_fn': total_fn,
                'total_fp': total_fp,
                'total_potential': total_potential,
                'overall_detection': overall_detection,
                'overall_precision': overall_precision,
                'overall_f1': overall_f1,
                'severity_stats': dict(severity_stats)
            },
            {
                'detection': chart_detection,
                'severity': chart_severity,
                'metrics': chart_metrics
            }
        )
        
        # Write HTML file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        console.print(f"[green]Report generated: {output_file}[/green]")
        return output_file
    
    def _generate_html(self, scores: List[Dict], stats: Dict, charts: Dict) -> str:
        """Generate the HTML content."""
        
        # CSS styles
        css = """
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #333;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px;
                text-align: center;
            }
            .header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
            }
            .header .subtitle {
                font-size: 1.2em;
                opacity: 0.95;
            }
            .content {
                padding: 40px;
            }
            .metric-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }
            .metric-card {
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                padding: 25px;
                border-radius: 12px;
                text-align: center;
                box-shadow: 0 4px 6px rgba(0,0,0,0.07);
                transition: transform 0.2s;
            }
            .metric-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 12px rgba(0,0,0,0.1);
            }
            .metric-card .value {
                font-size: 2.5em;
                font-weight: bold;
                margin: 10px 0;
            }
            .metric-card .label {
                color: #666;
                font-size: 0.9em;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .metric-card.success { background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%); }
            .metric-card.warning { background: linear-gradient(135deg, #ffeaa7 0%, #fdcb6e 100%); }
            .metric-card.danger { background: linear-gradient(135deg, #fd79a8 0%, #fdcb6e 100%); }
            .metric-card.info { background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); }
            
            .section {
                margin: 40px 0;
                background: #f8f9fa;
                border-radius: 8px;
                padding: 30px;
            }
            .section h2 {
                color: #667eea;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 2px solid #667eea;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
                background: white;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            }
            th {
                background: #667eea;
                color: white;
                padding: 15px;
                text-align: left;
                font-weight: 600;
            }
            td {
                padding: 12px 15px;
                border-bottom: 1px solid #e9ecef;
            }
            tr:last-child td {
                border-bottom: none;
            }
            tr:hover {
                background: #f8f9fa;
            }
            .severity-badge {
                display: inline-block;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 0.85em;
                font-weight: 600;
                text-transform: uppercase;
            }
            .severity-critical { background: #dc3545; color: white; }
            .severity-high { background: #fd7e14; color: white; }
            .severity-medium { background: #ffc107; color: #333; }
            .severity-low { background: #28a745; color: white; }
            .severity-unknown { background: #6c757d; color: white; }
            
            .dismissal-badge {
                display: inline-block;
                padding: 3px 8px;
                margin: 2px;
                border-radius: 12px;
                font-size: 0.75em;
                background: #e9ecef;
                color: #495057;
            }
            .confidence-high { color: #28a745; font-weight: bold; }
            .confidence-medium { color: #ffc107; font-weight: bold; }
            .confidence-low { color: #dc3545; font-weight: bold; }
            
            .chart-container {
                margin: 30px 0;
                text-align: center;
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            }
            .chart-container img {
                max-width: 100%;
                height: auto;
            }
            
            .finding-card {
                background: white;
                border-left: 4px solid #667eea;
                padding: 20px;
                margin: 15px 0;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            }
            .finding-card.matched {
                border-left-color: #28a745;
            }
            .finding-card.potential {
                border-left-color: #ffc107;
            }
            .finding-card.missed {
                border-left-color: #dc3545;
            }
            .finding-title {
                font-weight: bold;
                color: #333;
                margin-bottom: 10px;
            }
            .finding-details {
                color: #666;
                font-size: 0.9em;
            }
            .justification {
                background: #f8f9fa;
                padding: 10px;
                border-radius: 4px;
                margin-top: 10px;
                font-style: italic;
            }
            
            .info-panel {
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
            }
            .info-panel h3 {
                color: #667eea;
                margin-bottom: 10px;
            }
            .info-item {
                margin: 5px 0;
            }
            .info-label {
                font-weight: 600;
                color: #495057;
            }
            
            .footer {
                background: #f8f9fa;
                padding: 30px;
                text-align: center;
                color: #6c757d;
                border-top: 1px solid #dee2e6;
            }
            .footer a {
                color: #667eea;
                text-decoration: none;
            }
            .footer a:hover {
                text-decoration: underline;
            }
            
            @media (max-width: 768px) {
                .metric-grid {
                    grid-template-columns: 1fr;
                }
                .header h1 {
                    font-size: 1.8em;
                }
                .content {
                    padding: 20px;
                }
                table {
                    font-size: 0.9em;
                }
            }
        </style>
        """
        
        # Build HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ScaBench Security Analysis Report</title>
    {css}
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>ScaBench Security Analysis Report</h1>
            <div class="subtitle">
                {self.scan_info['tool_name']} {self.scan_info['tool_version']} | 
                Model: {self.scan_info['model']} | 
                {self.scan_info['scan_date']}
            </div>
        </div>
        
        <div class="content">
            <!-- Overall Metrics -->
            <div class="metric-grid">
                <div class="metric-card info">
                    <div class="label">Projects Analyzed</div>
                    <div class="value">{stats['total_projects']}</div>
                </div>
                <div class="metric-card">
                    <div class="label">Expected Vulnerabilities</div>
                    <div class="value">{stats['total_expected']}</div>
                </div>
                <div class="metric-card success">
                    <div class="label">True Positives</div>
                    <div class="value">{stats['total_tp']}</div>
                </div>
                <div class="metric-card danger">
                    <div class="label">False Negatives</div>
                    <div class="value">{stats['total_fn']}</div>
                </div>
                <div class="metric-card warning">
                    <div class="label">False Positives</div>
                    <div class="value">{stats['total_fp']}</div>
                </div>
                <div class="metric-card info">
                    <div class="label">Potential Matches</div>
                    <div class="value">{stats['total_potential']}</div>
                </div>
            </div>
            
            <!-- Performance Metrics -->
            <div class="section">
                <h2>Performance Metrics</h2>
                <div class="metric-grid">
                    <div class="metric-card">
                        <div class="label">Detection Rate</div>
                        <div class="value {'confidence-high' if stats['overall_detection'] > 50 else 'confidence-medium' if stats['overall_detection'] > 25 else 'confidence-low'}">
                            {stats['overall_detection']:.1f}%
                        </div>
                    </div>
                    <div class="metric-card">
                        <div class="label">Precision</div>
                        <div class="value {'confidence-high' if stats['overall_precision'] > 50 else 'confidence-medium' if stats['overall_precision'] > 25 else 'confidence-low'}">
                            {stats['overall_precision']:.1f}%
                        </div>
                    </div>
                    <div class="metric-card">
                        <div class="label">F1 Score</div>
                        <div class="value {'confidence-high' if stats['overall_f1'] > 50 else 'confidence-medium' if stats['overall_f1'] > 25 else 'confidence-low'}">
                            {stats['overall_f1']:.1f}%
                        </div>
                    </div>
                </div>
                
                {'<div class="chart-container"><img src="' + charts["metrics"] + '" alt="Performance Metrics"></div>' if charts.get("metrics") else ''}
            </div>
            
            <!-- Detection by Project -->
            <div class="section">
                <h2>Detection Rate by Project</h2>
                {'<div class="chart-container"><img src="' + charts["detection"] + '" alt="Detection by Project"></div>' if charts.get("detection") else ''}
                
                <table>
                    <thead>
                        <tr>
                            <th>Project</th>
                            <th>Expected</th>
                            <th>Found</th>
                            <th>True Positives</th>
                            <th>False Negatives</th>
                            <th>False Positives</th>
                            <th>Detection Rate</th>
                            <th>Precision</th>
                            <th>F1 Score</th>
                        </tr>
                    </thead>
                    <tbody>"""
        
        # Add project rows
        for score in scores:
            detection_class = 'confidence-high' if score['detection_rate'] > 0.5 else 'confidence-medium' if score['detection_rate'] > 0.25 else 'confidence-low'
            precision_class = 'confidence-high' if score['precision'] > 0.5 else 'confidence-medium' if score['precision'] > 0.25 else 'confidence-low'
            f1_class = 'confidence-high' if score['f1_score'] > 0.5 else 'confidence-medium' if score['f1_score'] > 0.25 else 'confidence-low'
            
            html += f"""
                        <tr>
                            <td><strong>{score['project']}</strong></td>
                            <td>{score['total_expected']}</td>
                            <td>{score['total_found']}</td>
                            <td style="color: #28a745;">{score['true_positives']}</td>
                            <td style="color: #dc3545;">{score['false_negatives']}</td>
                            <td style="color: #ffc107;">{score['false_positives']}</td>
                            <td class="{detection_class}">{score['detection_rate']*100:.1f}%</td>
                            <td class="{precision_class}">{score['precision']*100:.1f}%</td>
                            <td class="{f1_class}">{score['f1_score']*100:.1f}%</td>
                        </tr>"""
        
        html += """
                    </tbody>
                </table>
            </div>
            
            <!-- Severity Distribution -->
            <div class="section">
                <h2>Vulnerability Severity Distribution</h2>
                """ + (f'<div class="chart-container"><img src="{charts["severity"]}" alt="Severity Distribution"></div>' if charts.get("severity") else '') + """
                
                <table>
                    <thead>
                        <tr>
                            <th>Severity</th>
                            <th>Expected</th>
                            <th>Found (True Positives)</th>
                            <th>Detection Rate</th>
                        </tr>
                    </thead>
                    <tbody>"""
        
        # Add severity rows
        for severity in ['critical', 'high', 'medium', 'low']:
            sev_data = stats['severity_stats'].get(severity, {'expected': 0, 'found': 0})
            detection = (sev_data['found'] / sev_data['expected'] * 100) if sev_data['expected'] > 0 else 0
            
            html += f"""
                        <tr>
                            <td><span class="severity-badge severity-{severity}">{severity.upper()}</span></td>
                            <td>{sev_data['expected']}</td>
                            <td>{sev_data['found']}</td>
                            <td>{detection:.1f}%</td>
                        </tr>"""
        
        html += """
                    </tbody>
                </table>
            </div>
            
            <!-- Sample Findings -->
            <div class="section">
                <h2>Sample Findings</h2>
                
                <h3 style="color: #28a745; margin-top: 20px;">✓ Matched Findings (True Positives)</h3>"""
        
        # Show sample matched findings
        sample_count = 0
        for score in scores:
            for match in score.get('matched_findings', [])[:2]:  # Max 2 per project
                if sample_count >= 5:  # Total max 5
                    break
                html += f"""
                <div class="finding-card matched">
                    <div class="finding-title">
                        {match['expected']}
                    </div>
                    <div class="finding-details">
                        <strong>Matched with:</strong> {match['matched']}<br>
                        <strong>Confidence:</strong> <span class="confidence-high">{match['confidence']:.2f}</span><br>
                        <strong>Severity:</strong> <span class="severity-badge severity-{match.get('severity', 'unknown')}">{match.get('severity', 'unknown')}</span>
                    </div>
                    <div class="justification">
                        {match.get('justification', 'No justification provided')}
                    </div>
                </div>"""
                sample_count += 1
        
        html += """
                <h3 style="color: #ffc107; margin-top: 30px;">⚠ Potential Matches (Need Review)</h3>"""
        
        # Show sample potential matches
        sample_count = 0
        for score in scores:
            for match in score.get('potential_matches', [])[:2]:
                if sample_count >= 3:
                    break
                html += f"""
                <div class="finding-card potential">
                    <div class="finding-title">
                        {match['expected']}
                    </div>
                    <div class="finding-details">
                        <strong>Potentially matched with:</strong> {match['matched']}<br>
                        <strong>Confidence:</strong> <span class="confidence-medium">{match['confidence']:.2f}</span><br>
                        <strong>Severity:</strong> <span class="severity-badge severity-{match.get('severity', 'unknown')}">{match.get('severity', 'unknown')}</span>
                    </div>
                    {self._format_dismissal_reasons(match.get('dismissal_reasons', []))}
                    <div class="justification">
                        {match.get('justification', 'No justification provided')}
                    </div>
                </div>"""
                sample_count += 1
        
        html += """
                <h3 style="color: #dc3545; margin-top: 30px;">✗ Missed Findings (False Negatives)</h3>"""
        
        # Show sample missed findings
        sample_count = 0
        for score in scores:
            for miss in score.get('missed_findings', [])[:2]:
                if sample_count >= 5:
                    break
                html += f"""
                <div class="finding-card missed">
                    <div class="finding-title">
                        {miss['title']}
                    </div>
                    <div class="finding-details">
                        <strong>Severity:</strong> <span class="severity-badge severity-{miss.get('severity', 'unknown')}">{miss.get('severity', 'unknown')}</span><br>
                        <strong>Reason:</strong> {miss.get('reason', 'Not detected by tool')}
                    </div>
                </div>"""
                sample_count += 1
        
        html += """
            </div>
            
            <!-- Scan Information -->
            <div class="info-panel">
                <h3>Scan Information</h3>
                <div class="info-item">
                    <span class="info-label">Tool:</span> {self.scan_info['tool_name']} {self.scan_info['tool_version']}
                </div>
                <div class="info-item">
                    <span class="info-label">Model:</span> {self.scan_info['model']}
                </div>
                <div class="info-item">
                    <span class="info-label">Benchmark:</span> {self.scan_info['benchmark_version']}
                </div>
                <div class="info-item">
                    <span class="info-label">Date:</span> {self.scan_info['scan_date']}
                </div>"""
        
        if self.scan_info.get('notes'):
            html += f"""
                <div class="info-item">
                    <span class="info-label">Notes:</span> {self.scan_info['notes']}
                </div>"""
        
        html += f"""
            </div>
        </div>
        
        <div class="footer">
            <p>Generated by <a href="https://github.com/scabench">ScaBench</a> Report Generator</p>
            <p>Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>"""
        
        return html


def main():
    parser = argparse.ArgumentParser(
        description='Generate HTML reports from ScaBench scoring results',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--scores', '-s', required=True,
                       help='Directory containing score_*.json files')
    parser.add_argument('--benchmark', '-b',
                       help='Path to benchmark dataset (optional, for extra context)')
    parser.add_argument('--output', '-o', default='report.html',
                       help='Output HTML file (default: report.html)')
    parser.add_argument('--tool-name', default='Baseline Analyzer',
                       help='Name of the tool being evaluated')
    parser.add_argument('--tool-version', default='v1.0',
                       help='Version of the tool')
    parser.add_argument('--model', default='Not specified',
                       help='Model used for analysis')
    parser.add_argument('--notes',
                       help='Additional notes for the report')
    
    args = parser.parse_args()
    
    # Configuration
    config = {
        'tool_name': args.tool_name,
        'tool_version': args.tool_version,
        'model': args.model,
        'notes': args.notes or ''
    }
    
    # Generate report
    generator = ReportGenerator(config)
    
    scores_dir = Path(args.scores)
    if not scores_dir.exists():
        console.print(f"[red]Error: Scores directory not found: {scores_dir}[/red]")
        sys.exit(1)
    
    benchmark_file = Path(args.benchmark) if args.benchmark else None
    if benchmark_file and not benchmark_file.exists():
        console.print(f"[yellow]Warning: Benchmark file not found: {benchmark_file}[/yellow]")
        benchmark_file = None
    
    output_file = Path(args.output)
    
    try:
        report_path = generator.generate_report(scores_dir, benchmark_file, output_file)
        console.print(f"\n[bold green]Report successfully generated![/bold green]")
        console.print(f"View the report: [cyan]{report_path}[/cyan]")
    except Exception as e:
        console.print(f"[red]Error generating report: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()