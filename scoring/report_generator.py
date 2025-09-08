#!/usr/bin/env python3
"""
ScaBench Report Generator
Generate comprehensive HTML reports with advanced navigation, collapsible sections, and modern styling.
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


class ReportGenerator:
    """Generate HTML reports from ScaBench scoring results."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the report generator."""
        self.config = config or {}
        self.scan_info = {
            'tool_name': self.config.get('tool_name', 'Baseline Analyzer'),
            'tool_version': self.config.get('tool_version', 'v1.0'),
            'model': self.config.get('model', 'Not specified'),
            'scan_date': self.config.get('scan_date', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            'benchmark_version': self.config.get('benchmark_version', 'ScaBench v1.0'),
            'notes': self.config.get('notes', ''),
        }
    
    def _generate_mini_charts(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Generate compact inline SVG charts."""
        charts = {}
        
        # Detection rate circular progress chart
        detection_rate = data['overall_stats']['detection_rate']
        # Calculate the circumference for proper animation
        radius = 15.9155
        circumference = 2 * 3.14159 * radius
        offset = circumference - (detection_rate / 100 * circumference)
        
        # Determine color based on detection rate
        if detection_rate >= 70:
            stroke_color = '#10b981'  # Green
        elif detection_rate >= 40:
            stroke_color = '#f59e0b'  # Orange
        else:
            stroke_color = '#ef4444'  # Red
        
        charts['detection_pie'] = f"""
        <svg viewBox="0 0 36 36" class="circular-chart">
            <!-- Background circle -->
            <circle cx="18" cy="18" r="{radius}"
                fill="none"
                stroke="#f3f4f6"
                stroke-width="2.5" />
            
            <!-- Progress circle -->
            <circle cx="18" cy="18" r="{radius}"
                fill="none"
                stroke="{stroke_color}"
                stroke-width="3"
                stroke-dasharray="{circumference}"
                stroke-dashoffset="{offset}"
                stroke-linecap="round"
                transform="rotate(-90 18 18)"
                style="transition: stroke-dashoffset 1s ease-in-out;" />
            
            <!-- Inner circle for visual depth -->
            <circle cx="18" cy="18" r="13"
                fill="white"
                opacity="0.1" />
            
            <!-- Percentage text -->
            <text x="18" y="18" class="percentage" 
                text-anchor="middle" 
                dy=".3em"
                fill="{stroke_color}"
                font-size="7"
                font-weight="bold">{detection_rate:.1f}%</text>
        </svg>
        """
        
        # Severity distribution bar chart with both expected and found
        severity_data = data['severity_stats']
        max_val = max([severity_data.get(s, {}).get('expected', 0) 
                      for s in ['critical', 'high', 'medium', 'low']] + [1])
        
        charts['severity_bars'] = """<div class="mini-bar-chart">"""
        for sev, color in [('critical', '#ef4444'), ('high', '#f59e0b'), 
                          ('medium', '#3b82f6'), ('low', '#6b7280')]:
            expected = severity_data.get(sev, {}).get('expected', 0)
            found = severity_data.get(sev, {}).get('found', 0)
            height = (expected / max_val * 100) if max_val > 0 else 0
            found_height = (found / expected * 100) if expected > 0 else 0
            
            charts['severity_bars'] += f"""
            <div class="bar-wrapper">
                <div class="bar-container" style="height: {height}%;">
                    <div class="bar-expected" style="background: {color}20; border: 2px solid {color};">
                        <div class="bar-found" style="height: {found_height}%; background: {color};">
                            <span class="bar-value">{found}/{expected}</span>
                        </div>
                    </div>
                </div>
                <div class="bar-label">{sev.capitalize()}</div>
            </div>
            """
        charts['severity_bars'] += "</div>"
        
        return charts
    
    def _format_dismissal_reasons(self, reasons: List[str]) -> str:
        """Format dismissal reasons as styled badges."""
        if not reasons:
            return ''
        
        reason_map = {
            'different_root_cause': ('Different Root Cause', 'critical'),
            'different_location': ('Wrong Location', 'high'),
            'different_function': ('Wrong Function', 'high'),
            'different_contract': ('Wrong Contract', 'high'),
            'different_variable': ('Wrong Variables', 'medium'),
            'wrong_attack_vector': ('Wrong Attack Vector', 'critical'),
            'different_impact': ('Different Impact', 'medium'),
            'missing_identifiers': ('Missing Identifiers', 'low'),
            'general_description': ('Too Vague', 'low'),
            'not_found': ('Not Found', 'critical'),
            'matching_error': ('Matching Error', 'low')
        }
        
        badges_html = '<div class="dismissal-reasons">'
        for reason in reasons:
            label, severity = reason_map.get(reason, (reason, 'low'))
            badges_html += f'<span class="badge badge-{severity}">{label}</span>'
        badges_html += '</div>'
        return badges_html
    
    def generate_report(self, 
                       scores_path: Path,
                       benchmark_file: Optional[Path] = None,
                       output_file: Path = Path("report.html")) -> Path:
        """Generate HTML report from scoring results (single file or directory)."""
        console.print("Generating ScaBench report...")
        
        # Optional: load benchmark to filter which score files to include
        allowed_projects: Optional[set[str]] = None
        if benchmark_file and benchmark_file.exists():
            try:
                with open(benchmark_file, 'r') as bf:
                    bench = json.load(bf)
                if isinstance(bench, dict) and 'projects' in bench:
                    entries = bench['projects']
                elif isinstance(bench, list):
                    entries = bench
                else:
                    entries = []
                allowed_projects = set()
                for entry in entries:
                    pid = entry.get('project_id') or entry.get('id')
                    if isinstance(pid, str):
                        allowed_projects.add(pid)
                if not allowed_projects:
                    console.print("[yellow]Benchmark file provided but no project IDs found; skipping filter[/yellow]")
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to load benchmark file: {e}. Skipping filter.[/yellow]")

        # Determine if scores_path is a file or directory
        score_files = []
        if scores_path.is_file():
            # Single score file provided
            if scores_path.name.endswith('.json'):
                # Apply filter if benchmark provided
                if allowed_projects and scores_path.name.startswith('score_'):
                    pid = scores_path.stem[6:]
                    if pid in allowed_projects:
                        score_files = [scores_path]
                    else:
                        console.print(f"[yellow]Skipping {scores_path.name} (not in benchmark)[/yellow]")
                        score_files = []
                else:
                    score_files = [scores_path]
            else:
                console.print(f"[red]Invalid file: {scores_path} (must be .json)[/red]")
                sys.exit(1)
        elif scores_path.is_dir():
            # Directory provided - look for score files
            score_files = list(scores_path.glob("score_*.json"))
            # Apply benchmark filter if provided
            if allowed_projects:
                filtered = []
                for sf in score_files:
                    stem = sf.stem
                    pid = stem[6:] if stem.startswith('score_') else stem
                    if pid in allowed_projects:
                        filtered.append(sf)
                score_files = filtered
            if not score_files:
                console.print(f"[red]No score_*.json files found in {scores_path} after filtering[/red]")
                sys.exit(1)
        else:
            console.print(f"[red]Path not found: {scores_path}[/red]")
            sys.exit(1)
        
        all_scores = []
        for score_file in sorted(score_files):
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
        overall_precision = (total_tp / (total_tp + total_fp) * 100) if (total_tp + total_fp) > 0 else 0
        overall_f1 = (2 * overall_precision * overall_detection / 
                     (overall_precision + overall_detection)) if (overall_precision + overall_detection) > 0 else 0
        
        # Severity statistics
        severity_stats = defaultdict(lambda: {'expected': 0, 'found': 0})
        for score in all_scores:
            for miss in score.get('missed_findings', []):
                severity = miss.get('severity', 'unknown').lower()
                severity_stats[severity]['expected'] += 1
            for match in score.get('matched_findings', []):
                severity = match.get('severity', 'unknown').lower()
                severity_stats[severity]['found'] += 1
                severity_stats[severity]['expected'] += 1
        
        # Prepare chart data
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
        
        # Generate mini charts
        charts = self._generate_mini_charts(chart_data)
        
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
            charts
        )
        
        # Write HTML file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        console.print(f"Report generated: {output_file}")
        return output_file
    
    def _generate_html(self, scores: List[Dict], stats: Dict, charts: Dict) -> str:
        """Generate the HTML content."""
        
        # Modern, beautiful CSS with animations and gradients
        css = """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
            
            * { 
                margin: 0; 
                padding: 0; 
                box-sizing: border-box; 
            }
            
            :root {
                --primary: #6366f1;
                --primary-dark: #4f46e5;
                --secondary: #8b5cf6;
                --success: #10b981;
                --warning: #f59e0b;
                --danger: #ef4444;
                --dark: #1f2937;
                --light: #f9fafb;
                --border: #e5e7eb;
            }
            
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                line-height: 1.6;
                color: var(--dark);
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 0;
                margin: 0;
            }
            
            /* Navigation */
            .nav-container {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(10px);
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                z-index: 1000;
                transition: all 0.3s ease;
            }
            
            .nav {
                max-width: 1400px;
                margin: 0 auto;
                padding: 1rem 2rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .nav-title {
                font-size: 1.25rem;
                font-weight: 600;
                background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            
            .nav-links {
                display: flex;
                gap: 2rem;
                list-style: none;
            }
            
            .nav-links a {
                color: var(--dark);
                text-decoration: none;
                font-weight: 500;
                transition: color 0.3s ease;
                position: relative;
            }
            
            .nav-links a:hover {
                color: var(--primary);
            }
            
            .nav-links a::after {
                content: '';
                position: absolute;
                bottom: -5px;
                left: 0;
                width: 0;
                height: 2px;
                background: var(--primary);
                transition: width 0.3s ease;
            }
            
            .nav-links a:hover::after {
                width: 100%;
            }
            
            /* Main Container */
            .container {
                max-width: 1400px;
                margin: 80px auto 40px;
                padding: 0 20px;
            }
            
            /* Hero Section */
            .hero {
                background: white;
                border-radius: 20px;
                padding: 3rem;
                margin-bottom: 2rem;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                position: relative;
                overflow: hidden;
            }
            
            .hero::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 5px;
                background: linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%);
            }
            
            .hero h1 {
                font-size: 3rem;
                font-weight: 700;
                margin-bottom: 1rem;
                background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            
            .scan-info {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 1rem;
                margin-top: 2rem;
                padding-top: 2rem;
                border-top: 1px solid var(--border);
            }
            
            .scan-info-item {
                display: flex;
                flex-direction: column;
            }
            
            .scan-info-label {
                font-size: 0.875rem;
                color: #6b7280;
                margin-bottom: 0.25rem;
            }
            
            .scan-info-value {
                font-weight: 600;
                color: var(--dark);
            }
            
            /* Metrics Dashboard */
            .metrics-dashboard {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 1.5rem;
                margin-bottom: 2rem;
            }
            
            .metric-card {
                background: white;
                border-radius: 16px;
                padding: 1.5rem;
                box-shadow: 0 4px 6px rgba(0,0,0,0.07);
                position: relative;
                transition: all 0.3s ease;
                cursor: pointer;
            }
            
            .metric-card:hover {
                transform: translateY(-4px);
                box-shadow: 0 12px 24px rgba(0,0,0,0.15);
            }
            
            .metric-card.primary {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            
            .metric-card.success {
                background: linear-gradient(135deg, #34d399 0%, #10b981 100%);
                color: white;
            }
            
            .metric-card.warning {
                background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
                color: white;
            }
            
            .metric-card.danger {
                background: linear-gradient(135deg, #f87171 0%, #ef4444 100%);
                color: white;
            }
            
            .metric-icon {
                position: absolute;
                top: 1.5rem;
                right: 1.5rem;
                font-size: 2rem;
                opacity: 0.3;
            }
            
            .metric-value {
                font-size: 2.5rem;
                font-weight: 700;
                margin: 0.5rem 0;
            }
            
            .metric-label {
                font-size: 0.875rem;
                opacity: 0.9;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            .metric-trend {
                margin-top: 0.5rem;
                font-size: 0.875rem;
                opacity: 0.8;
            }
            
            /* Charts Section */
            .charts-section {
                background: white;
                border-radius: 16px;
                padding: 2rem;
                margin-bottom: 2rem;
                box-shadow: 0 4px 6px rgba(0,0,0,0.07);
            }
            
            .charts-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 2rem;
                margin-top: 1.5rem;
            }
            
            .chart-container {
                text-align: center;
            }
            
            .chart-title {
                font-weight: 600;
                margin-bottom: 1rem;
                color: var(--dark);
            }
            
            /* Mini Charts */
            .circular-chart {
                width: 140px;
                height: 140px;
                filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.1));
                animation: fadeIn 0.6s ease-out;
            }
            
            .circular-chart circle {
                animation: drawCircle 1.5s ease-out forwards;
            }
            
            .percentage {
                animation: fadeIn 1s ease-out 0.5s both;
            }
            
            @keyframes drawCircle {
                from {
                    stroke-dashoffset: 100;
                    opacity: 0;
                }
                to {
                    opacity: 1;
                }
            }
            
            .mini-bar-chart {
                display: flex;
                justify-content: space-around;
                align-items: flex-end;
                height: 140px;
                padding: 10px;
                gap: 15px;
            }
            
            .bar-wrapper {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: flex-end;
                height: 100%;
            }
            
            .bar-container {
                width: 100%;
                display: flex;
                align-items: flex-end;
                position: relative;
            }
            
            .bar-expected {
                width: 100%;
                height: 100%;
                border-radius: 8px 8px 0 0;
                position: relative;
                overflow: hidden;
                display: flex;
                align-items: flex-end;
                transition: all 0.3s ease;
            }
            
            .bar-found {
                width: 100%;
                border-radius: 6px 6px 0 0;
                position: relative;
                display: flex;
                align-items: center;
                justify-content: center;
                animation: grow 1.2s ease-out;
                transition: all 0.3s ease;
            }
            
            .bar-wrapper:hover .bar-found {
                filter: brightness(1.1);
                transform: translateY(-2px);
            }
            
            .bar-value {
                color: white;
                font-weight: 700;
                font-size: 0.7rem;
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
                white-space: nowrap;
            }
            
            .bar-label {
                margin-top: 8px;
                font-size: 0.75rem;
                font-weight: 600;
                color: var(--dark);
                text-align: center;
            }
            
            /* Projects Section */
            .projects-section {
                background: white;
                border-radius: 16px;
                padding: 2rem;
                margin-bottom: 2rem;
                box-shadow: 0 4px 6px rgba(0,0,0,0.07);
            }
            
            .section-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1.5rem;
                padding-bottom: 1rem;
                border-bottom: 2px solid var(--border);
            }
            
            .section-title {
                font-size: 1.5rem;
                font-weight: 700;
                color: var(--dark);
            }
            
            .filter-buttons {
                display: flex;
                gap: 0.5rem;
            }
            
            .filter-btn {
                padding: 0.5rem 1rem;
                border: 2px solid var(--border);
                background: white;
                border-radius: 8px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            
            .filter-btn:hover {
                border-color: var(--primary);
                color: var(--primary);
            }
            
            .filter-btn.active {
                background: var(--primary);
                color: white;
                border-color: var(--primary);
            }
            
            /* Project Cards */
            .project-card {
                background: var(--light);
                border: 1px solid var(--border);
                border-radius: 12px;
                margin-bottom: 1rem;
                overflow: hidden;
                transition: all 0.3s ease;
            }
            
            .project-card:hover {
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            }
            
            .project-header {
                padding: 1.25rem;
                background: white;
                display: flex;
                justify-content: space-between;
                align-items: center;
                cursor: pointer;
                user-select: none;
            }
            
            .project-header:hover {
                background: var(--light);
            }
            
            .project-name {
                font-weight: 600;
                font-size: 1.1rem;
                color: var(--dark);
            }
            
            .project-stats {
                display: flex;
                gap: 1.5rem;
                align-items: center;
            }
            
            .stat-item {
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            
            .stat-value {
                font-weight: 700;
                font-size: 1.25rem;
            }
            
            .stat-label {
                font-size: 0.75rem;
                color: #6b7280;
                text-transform: uppercase;
            }
            
            .expand-icon {
                font-size: 1.25rem;
                transition: transform 0.3s ease;
            }
            
            .project-card.expanded .expand-icon {
                transform: rotate(180deg);
            }
            
            .project-details {
                display: none;
                transition: all 0.3s ease;
            }
            
            .project-card.expanded .project-details {
                display: block;
            }
            
            .project-details .details-wrapper {
                padding: 1.5rem;
                border-top: 1px solid var(--border);
            }
            
            /* Findings Tabs */
            .tabs {
                display: flex;
                gap: 0.5rem;
                margin-bottom: 1.5rem;
                border-bottom: 2px solid var(--border);
            }
            
            .tab {
                padding: 0.75rem 1.5rem;
                background: none;
                border: none;
                font-weight: 500;
                color: #6b7280;
                cursor: pointer;
                position: relative;
                transition: all 0.3s ease;
            }
            
            .tab:hover {
                color: var(--primary);
            }
            
            .tab.active {
                color: var(--primary);
            }
            
            .tab.active::after {
                content: '';
                position: absolute;
                bottom: -2px;
                left: 0;
                right: 0;
                height: 2px;
                background: var(--primary);
            }
            
            .tab-badge {
                display: inline-block;
                margin-left: 0.5rem;
                padding: 0.125rem 0.5rem;
                background: var(--primary);
                color: white;
                border-radius: 12px;
                font-size: 0.75rem;
                font-weight: 600;
            }
            
            .tab-content {
                display: none;
            }
            
            .tab-content.active {
                display: block;
                animation: fadeIn 0.3s ease;
            }
            
            /* Finding Cards */
            .finding-card {
                background: white;
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 1rem;
                margin-bottom: 1rem;
                transition: all 0.3s ease;
            }
            
            .finding-card:hover {
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            
            /* Expandable details */
            .details-toggle {
                cursor: pointer;
                color: var(--primary);
                font-size: 0.9rem;
                margin-top: 0.5rem;
                display: inline-flex;
                align-items: center;
                gap: 0.3rem;
                transition: color 0.2s;
            }
            
            .details-toggle:hover {
                color: var(--primary-dark);
            }
            
            .details-toggle::before {
                content: '▶';
                display: inline-block;
                transition: transform 0.2s;
            }
            
            .details-toggle.expanded::before {
                transform: rotate(90deg);
            }
            
            .details-content {
                display: none;
                margin-top: 1rem;
                padding-top: 1rem;
                border-top: 1px solid var(--border);
            }
            
            .details-content.show {
                display: block;
                animation: slideDown 0.3s ease;
            }
            
            @keyframes slideDown {
                from {
                    opacity: 0;
                    transform: translateY(-10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            .detail-section {
                margin-bottom: 1rem;
            }
            
            .detail-section h4 {
                color: #4b5563;
                font-size: 0.9rem;
                font-weight: 600;
                margin-bottom: 0.5rem;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .detail-section .content {
                background: #f9fafb;
                padding: 0.75rem;
                border-radius: 6px;
                font-size: 0.9rem;
                line-height: 1.6;
                color: #374151;
                white-space: pre-wrap;
                word-wrap: break-word;
            }
            
            .finding-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 0.75rem;
            }
            
            .finding-title {
                font-weight: 600;
                color: var(--dark);
                flex: 1;
                margin-right: 1rem;
            }
            
            .severity-badge {
                padding: 0.25rem 0.75rem;
                border-radius: 6px;
                font-size: 0.75rem;
                font-weight: 600;
                text-transform: uppercase;
            }
            
            .severity-critical {
                background: #fee2e2;
                color: #dc2626;
            }
            
            .severity-high {
                background: #fed7aa;
                color: #ea580c;
            }
            
            .severity-medium {
                background: #fef3c7;
                color: #d97706;
            }
            
            .severity-low {
                background: #dbeafe;
                color: #2563eb;
            }
            
            .justification-box {
                background: var(--light);
                border-left: 4px solid var(--primary);
                padding: 0.75rem 1rem;
                margin-top: 0.75rem;
                border-radius: 4px;
                font-size: 0.9rem;
                line-height: 1.6;
                color: #4b5563;
            }
            
            .confidence-indicator {
                display: inline-block;
                margin-left: 0.5rem;
                padding: 0.125rem 0.5rem;
                background: var(--success);
                color: white;
                border-radius: 4px;
                font-size: 0.75rem;
                font-weight: 600;
            }
            
            .dismissal-reasons {
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
                margin-top: 0.75rem;
            }
            
            .badge {
                padding: 0.25rem 0.75rem;
                border-radius: 6px;
                font-size: 0.75rem;
                font-weight: 500;
            }
            
            .badge-critical {
                background: #fee2e2;
                color: #dc2626;
            }
            
            .badge-high {
                background: #fed7aa;
                color: #ea580c;
            }
            
            .badge-medium {
                background: #fef3c7;
                color: #d97706;
            }
            
            .badge-low {
                background: #e0e7ff;
                color: #4338ca;
            }
            
            /* Animations */
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            @keyframes grow {
                from { height: 0; }
                to { height: auto; }
            }
            
            @keyframes progress {
                from { stroke-dasharray: 0 100; }
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                .nav-links {
                    display: none;
                }
                
                .hero h1 {
                    font-size: 2rem;
                }
                
                .metrics-dashboard {
                    grid-template-columns: 1fr;
                }
                
                .project-stats {
                    flex-direction: column;
                    gap: 0.5rem;
                }
            }
            
            /* Print Styles */
            @media print {
                .nav-container {
                    position: relative;
                }
                
                .filter-buttons,
                .expand-icon {
                    display: none;
                }
                
                .project-details {
                    max-height: none !important;
                }
            }
        </style>
        """
        
        # JavaScript for interactivity
        javascript = """
        <script>
            // Toggle project details
            function toggleProject(element) {
                console.log('Toggle clicked');
                const card = element.closest('.project-card');
                if (!card) {
                    console.error('Could not find project-card');
                    return;
                }
                card.classList.toggle('expanded');
                console.log('Card expanded:', card.classList.contains('expanded'));
            }
            
            // Tab switching
            function switchTab(projectId, tabName) {
                const project = document.getElementById(projectId);
                
                // Update tab styles
                project.querySelectorAll('.tab').forEach(tab => {
                    tab.classList.remove('active');
                });
                event.target.classList.add('active');
                
                // Update content
                project.querySelectorAll('.tab-content').forEach(content => {
                    content.classList.remove('active');
                });
                project.querySelector(`.tab-content[data-tab="${tabName}"]`).classList.add('active');
            }
            
            // Toggle details expansion for findings
            function toggleDetails(id) {
                const content = document.getElementById(id);
                const toggle = content.previousElementSibling;
                
                if (content.classList.contains('show')) {
                    content.classList.remove('show');
                    toggle.classList.remove('expanded');
                } else {
                    content.classList.add('show');
                    toggle.classList.add('expanded');
                }
            }
            
            // Filter projects
            function filterProjects(filter) {
                const cards = document.querySelectorAll('.project-card');
                
                // Update button styles
                document.querySelectorAll('.filter-btn').forEach(btn => {
                    btn.classList.remove('active');
                });
                event.target.classList.add('active');
                
                // Filter cards
                cards.forEach(card => {
                    if (filter === 'all') {
                        card.style.display = 'block';
                    } else if (filter === 'detected') {
                        const rate = parseFloat(card.dataset.detectionRate);
                        card.style.display = rate > 0 ? 'block' : 'none';
                    } else if (filter === 'missed') {
                        const rate = parseFloat(card.dataset.detectionRate);
                        card.style.display = rate === 0 ? 'block' : 'none';
                    }
                });
            }
            
            // Smooth scroll for navigation
            document.addEventListener('DOMContentLoaded', function() {
                document.querySelectorAll('a[href^="#"]').forEach(anchor => {
                    anchor.addEventListener('click', function (e) {
                        e.preventDefault();
                        const target = document.querySelector(this.getAttribute('href'));
                        if (target) {
                            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }
                    });
                });
            });
            
            // Sticky navigation on scroll
            window.addEventListener('scroll', function() {
                const nav = document.querySelector('.nav-container');
                if (window.scrollY > 100) {
                    nav.style.boxShadow = '0 4px 20px rgba(0,0,0,0.1)';
                } else {
                    nav.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
                }
            });
        </script>
        """
        
        # Build HTML content
        html_parts = [
            '<!DOCTYPE html>',
            '<html lang="en">',
            '<head>',
            '<meta charset="UTF-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            '<title>ScaBench Security Tool Benchmark Report</title>',
            css,
            '</head>',
            '<body>',
            
            # SVG Gradient Definition
            '''<svg style="display: none;">
                <defs>
                    <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" style="stop-color:#667eea;stop-opacity:1" />
                        <stop offset="100%" style="stop-color:#764ba2;stop-opacity:1" />
                    </linearGradient>
                </defs>
            </svg>''',
            
            # Navigation
            '<div class="nav-container">',
            '<nav class="nav">',
            '<div class="nav-title">🎯 ScaBench</div>',
            '<ul class="nav-links">',
            '<li><a href="#overview">Overview</a></li>',
            '<li><a href="#metrics">Metrics</a></li>',
            '<li><a href="#projects">Projects</a></li>',
            '<li><a href="#charts">Analysis</a></li>',
            '</ul>',
            '</nav>',
            '</div>',
            
            # Container
            '<div class="container">',
            
            # Hero Section
            '<section id="overview" class="hero">',
            '<h1>ScaBench Security Tool Benchmark Report</h1>',
            '<p style="font-size: 1.1rem; color: #6b7280; margin-bottom: 2rem;">',
            f'Comprehensive benchmark evaluation across {stats["total_projects"]} projects with {stats["total_expected"]} known vulnerabilities',
            '</p>',
            '<div class="scan-info">',
            f'<div class="scan-info-item"><span class="scan-info-label">Tool</span><span class="scan-info-value">{self.scan_info["tool_name"]}</span></div>',
            f'<div class="scan-info-item"><span class="scan-info-label">Model</span><span class="scan-info-value">{self.scan_info["model"]}</span></div>',
            f'<div class="scan-info-item"><span class="scan-info-label">Date</span><span class="scan-info-value">{self.scan_info["scan_date"]}</span></div>',
            f'<div class="scan-info-item"><span class="scan-info-label">Benchmark</span><span class="scan-info-value">{self.scan_info["benchmark_version"]}</span></div>',
            '</div>',
            '</section>',
            
            # Metrics Dashboard
            '<section id="metrics" class="metrics-dashboard">',
            f'''<div class="metric-card primary">
                <div class="metric-icon">📊</div>
                <div class="metric-value">{stats["total_projects"]}</div>
                <div class="metric-label">Projects Analyzed</div>
                <div class="metric-trend">Full benchmark coverage</div>
            </div>''',
            f'''<div class="metric-card">
                <div class="metric-icon">🎯</div>
                <div class="metric-value">{stats["total_expected"]}</div>
                <div class="metric-label">Expected Vulnerabilities</div>
                <div class="metric-trend">From benchmark dataset</div>
            </div>''',
            f'''<div class="metric-card success">
                <div class="metric-icon">✅</div>
                <div class="metric-value">{stats["total_tp"]}</div>
                <div class="metric-label">True Positives</div>
                <div class="metric-trend">{stats["overall_detection"]:.1f}% detection rate</div>
            </div>''',
            f'''<div class="metric-card warning">
                <div class="metric-icon">⚠️</div>
                <div class="metric-value">{stats["total_fn"]}</div>
                <div class="metric-label">False Negatives</div>
                <div class="metric-trend">Missed vulnerabilities</div>
            </div>''',
            f'''<div class="metric-card danger">
                <div class="metric-icon">❌</div>
                <div class="metric-value">{stats["total_fp"]}</div>
                <div class="metric-label">False Positives</div>
                <div class="metric-trend">Incorrect detections</div>
            </div>''',
            f'''<div class="metric-card">
                <div class="metric-icon">📈</div>
                <div class="metric-value">{stats["overall_f1"]:.1f}%</div>
                <div class="metric-label">F1 Score</div>
                <div class="metric-trend">Overall performance</div>
            </div>''',
            '</section>',
            
            # Charts Section
            '<section id="charts" class="charts-section">',
            '<div class="section-header">',
            '<h2 class="section-title">Performance Analysis</h2>',
            '</div>',
            '<div class="charts-grid">',
            '<div class="chart-container">',
            '<div class="chart-title">Overall Detection Rate</div>',
            charts['detection_pie'],
            '</div>',
            '<div class="chart-container">',
            '<div class="chart-title">Severity Distribution</div>',
            charts['severity_bars'],
            '</div>',
            '</div>',
            '</section>',
            
            # Projects Section
            '<section id="projects" class="projects-section">',
            '<div class="section-header">',
            '<h2 class="section-title">Project Details</h2>',
            '<div class="filter-buttons">',
            '<button class="filter-btn active" onclick="filterProjects(\'all\')">All Projects</button>',
            '<button class="filter-btn" onclick="filterProjects(\'detected\')">With Detections</button>',
            '<button class="filter-btn" onclick="filterProjects(\'missed\')">No Detections</button>',
            '</div>',
            '</div>',
        ]
        
        # Add project cards
        for i, score in enumerate(scores):
            project_id = f"project-{i}"
            detection_rate = score['detection_rate'] * 100
            
            html_parts.append(f'''
            <div class="project-card" id="{project_id}" data-detection-rate="{detection_rate}">
                <div class="project-header" onclick="toggleProject(this)">
                    <div class="project-name">{score['project']}</div>
                    <div class="project-stats">
                        <div class="stat-item">
                            <div class="stat-value" style="color: var(--primary);">{score['total_expected']}</div>
                            <div class="stat-label">Expected</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value" style="color: var(--success);">{score['true_positives']}</div>
                            <div class="stat-label">Found</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value" style="color: {self._get_rate_color(detection_rate)};">{detection_rate:.1f}%</div>
                            <div class="stat-label">Detection</div>
                        </div>
                        <div class="expand-icon">▼</div>
                    </div>
                </div>
                <div class="project-details">
                    <div class="details-wrapper">
                        <div class="tabs">
                            <button class="tab active" onclick="switchTab('{project_id}', 'matched')">
                                Matched<span class="tab-badge">{score['true_positives']}</span>
                            </button>
                            <button class="tab" onclick="switchTab('{project_id}', 'missed')">
                                Missed<span class="tab-badge">{score['false_negatives']}</span>
                            </button>
                            <button class="tab" onclick="switchTab('{project_id}', 'extra')">
                                Extra<span class="tab-badge">{score['false_positives']}</span>
                            </button>
                            <button class="tab" onclick="switchTab('{project_id}', 'potential')">
                                Potential<span class="tab-badge">{len(score.get('potential_matches', []))}</span>
                            </button>
                        </div>
            ''')
            
            # Matched findings tab
            html_parts.append('<div class="tab-content active" data-tab="matched">')
            if score['matched_findings']:
                for idx, match in enumerate(score['matched_findings']):
                    severity = match.get('severity', 'unknown').lower()
                    confidence = match.get('confidence', 1.0)
                    finding_id = match.get('id', f'{project_id}_match_{idx}')
                    
                    # Escape descriptions for HTML
                    import html as html_lib
                    expected_desc = html_lib.escape(match.get('expected_description', 'No description available'))
                    found_desc = html_lib.escape(match.get('found_description', 'No description available'))
                    matched_title = html_lib.escape(match.get('matched', 'Unknown'))
                    
                    html_parts.append(f'''
                    <div class="finding-card">
                        <div class="finding-header">
                            <div class="finding-title">
                                {match.get('expected', 'Unknown')}
                                <span class="confidence-indicator">{int(confidence*100)}% Match</span>
                            </div>
                            <span class="severity-badge severity-{severity}">{severity}</span>
                        </div>
                        <div class="justification-box">
                            <strong>Justification:</strong> {match.get('justification', 'No justification provided')}
                        </div>
                        <span class="details-toggle" onclick="toggleDetails('{finding_id}')">
                            View Full Descriptions
                        </span>
                        <div id="{finding_id}" class="details-content">
                            <div class="detail-section">
                                <h4>Expected Finding</h4>
                                <div class="content">
                                    <strong>Title:</strong> {match.get('expected', 'Unknown')}<br><br>
                                    <strong>Description:</strong><br>
                                    {expected_desc}
                                </div>
                            </div>
                            <div class="detail-section">
                                <h4>Tool Finding (Matched)</h4>
                                <div class="content">
                                    <strong>Title:</strong> {matched_title}<br><br>
                                    <strong>Description:</strong><br>
                                    {found_desc}
                                </div>
                            </div>
                            <div class="detail-section">
                                <h4>Match Details</h4>
                                <div class="content">
                                    <strong>Finding ID:</strong> {finding_id}<br>
                                    <strong>Confidence:</strong> {confidence:.2f}<br>
                                    <strong>Tool Finding Index:</strong> {match.get('tool_finding_index', 'N/A')}
                                </div>
                            </div>
                        </div>
                    </div>
                    ''')
            else:
                html_parts.append('<p style="color: #6b7280; text-align: center; padding: 2rem;">No matched vulnerabilities</p>')
            html_parts.append('</div>')
            
            # Missed findings tab
            html_parts.append('<div class="tab-content" data-tab="missed">')
            if score['missed_findings']:
                for idx, miss in enumerate(score['missed_findings']):
                    severity = miss.get('severity', 'unknown').lower()
                    finding_id = miss.get('id', f'{project_id}_miss_{idx}')
                    
                    # Escape description for HTML
                    import html as html_lib
                    description = html_lib.escape(miss.get('description', 'No description available'))
                    
                    html_parts.append(f'''
                    <div class="finding-card">
                        <div class="finding-header">
                            <div class="finding-title">{miss.get('title', 'Unknown')}</div>
                            <span class="severity-badge severity-{severity}">{severity}</span>
                        </div>
                        <div class="justification-box">
                            <strong>Reason:</strong> {miss.get('reason', 'Not detected by tool')}
                        </div>
                        <span class="details-toggle" onclick="toggleDetails('{finding_id}_miss')">
                            View Full Description
                        </span>
                        <div id="{finding_id}_miss" class="details-content">
                            <div class="detail-section">
                                <h4>Expected Finding Description</h4>
                                <div class="content">
                                    <strong>Title:</strong> {miss.get('title', 'Unknown')}<br><br>
                                    <strong>Description:</strong><br>
                                    {description}
                                </div>
                            </div>
                            <div class="detail-section">
                                <h4>Detection Details</h4>
                                <div class="content">
                                    <strong>Finding ID:</strong> {finding_id}<br>
                                    <strong>Status:</strong> Not Detected<br>
                                    <strong>Reason:</strong> {miss.get('reason', 'Not detected by tool')}
                                </div>
                            </div>
                        </div>
                    </div>
                    ''')
            else:
                html_parts.append('<p style="color: #6b7280; text-align: center; padding: 2rem;">No missed vulnerabilities</p>')
            html_parts.append('</div>')
            
            # Extra findings tab
            html_parts.append('<div class="tab-content" data-tab="extra">')
            if score['extra_findings']:
                for idx, extra in enumerate(score['extra_findings']):
                    severity = extra.get('severity', 'unknown').lower()
                    finding_id = extra.get('id', f'{project_id}_extra_{idx}')
                    
                    # Escape description for HTML
                    import html as html_lib
                    description = html_lib.escape(extra.get('description', 'No description available'))
                    
                    html_parts.append(f'''
                    <div class="finding-card">
                        <div class="finding-header">
                            <div class="finding-title">{extra.get('title', 'Unknown')}</div>
                            <span class="severity-badge severity-{severity}">{severity}</span>
                        </div>
                        <span class="details-toggle" onclick="toggleDetails('{finding_id}_extra')">
                            View Full Description
                        </span>
                        <div id="{finding_id}_extra" class="details-content">
                            <div class="detail-section">
                                <h4>Tool Finding Description</h4>
                                <div class="content">
                                    <strong>Title:</strong> {extra.get('title', 'Unknown')}<br><br>
                                    <strong>Description:</strong><br>
                                    {description}
                                </div>
                            </div>
                            <div class="detail-section">
                                <h4>Detection Details</h4>
                                <div class="content">
                                    <strong>Finding ID:</strong> {finding_id}<br>
                                    <strong>Original ID:</strong> {extra.get('original_id', 'N/A')}<br>
                                    <strong>Status:</strong> False Positive (not in expected findings)
                                </div>
                            </div>
                        </div>
                    </div>
                    ''')
            else:
                html_parts.append('<p style="color: #6b7280; text-align: center; padding: 2rem;">No extra findings</p>')
            html_parts.append('</div>')
            
            # Potential matches tab
            html_parts.append('<div class="tab-content" data-tab="potential">')
            if score.get('potential_matches'):
                for pot in score['potential_matches']:
                    confidence = pot.get('confidence', 0) * 100
                    html_parts.append(f'''
                    <div class="finding-card">
                        <div class="finding-header">
                            <div class="finding-title">
                                {pot.get('expected_title', 'Unknown')}
                                <span class="confidence-indicator" style="background: var(--warning);">{confidence:.0f}% Confidence</span>
                            </div>
                        </div>
                        {self._format_dismissal_reasons(pot.get('dismissal_reasons', []))}
                        <div class="justification-box">
                            <strong>Analysis:</strong> {pot.get('justification', 'Requires manual review')}
                        </div>
                    </div>
                    ''')
            else:
                html_parts.append('<p style="color: #6b7280; text-align: center; padding: 2rem;">No potential matches</p>')
            html_parts.append('</div>')
            
            html_parts.append('</div></div></div>')
        
        html_parts.extend([
            '</section>',
            '</div>',  # container
            javascript,
            '</body>',
            '</html>'
        ])
        
        return '\n'.join(html_parts)
    
    def _get_rate_color(self, rate: float) -> str:
        """Get color based on detection rate."""
        if rate >= 70:
            return 'var(--success)'
        elif rate >= 40:
            return 'var(--warning)'
        else:
            return 'var(--danger)'


def main():
    parser = argparse.ArgumentParser(description='Generate ScaBench HTML reports')
    parser.add_argument('--scores', required=True, help='Path to score JSON file or directory containing score_*.json files')
    parser.add_argument('--output', default='report.html', help='Output HTML file')
    parser.add_argument('--tool-name', default='Security Analyzer', help='Name of the tool')
    parser.add_argument('--model', default='Not specified', help='Model used for analysis')
    parser.add_argument('--benchmark', help='Optional benchmark dataset file')
    
    args = parser.parse_args()
    
    config = {
        'tool_name': args.tool_name,
        'model': args.model,
    }
    
    generator = ReportGenerator(config)
    generator.generate_report(
        Path(args.scores),
        Path(args.benchmark) if args.benchmark else None,
        Path(args.output)
    )
    
    console.print("\nReport successfully generated")
    console.print(f"View the report: {args.output}")


if __name__ == "__main__":
    main()
