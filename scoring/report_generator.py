#!/usr/bin/env python3
"""
ScaBench Report Generator - Enhanced Beautiful Version
Generate comprehensive HTML reports with advanced navigation, collapsible sections, and beautiful styling.
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
    """Generate beautiful HTML reports from ScaBench scoring results."""
    
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
        
        # Detection rate pie chart
        detection_rate = data['overall_stats']['detection_rate']
        charts['detection_pie'] = f"""
        <svg viewBox="0 0 36 36" class="circular-chart">
            <path class="circle-bg" d="M18 2.0845
                a 15.9155 15.9155 0 0 1 0 31.831
                a 15.9155 15.9155 0 0 1 0 -31.831" />
            <path class="circle" stroke-dasharray="{detection_rate}, 100" d="M18 2.0845
                a 15.9155 15.9155 0 0 1 0 31.831
                a 15.9155 15.9155 0 0 1 0 -31.831" />
            <text x="18" y="21" class="percentage">{detection_rate:.1f}%</text>
        </svg>
        """
        
        # Severity distribution bar chart
        severity_data = data['severity_stats']
        max_val = max([severity_data.get(s, {}).get('expected', 0) 
                      for s in ['critical', 'high', 'medium', 'low']] + [1])
        
        charts['severity_bars'] = """<div class="mini-bar-chart">"""
        for sev, color in [('critical', '#e74c3c'), ('high', '#f39c12'), 
                          ('medium', '#3498db'), ('low', '#95a5a6')]:
            val = severity_data.get(sev, {}).get('expected', 0)
            height = (val / max_val * 100) if max_val > 0 else 0
            charts['severity_bars'] += f"""
            <div class="bar-wrapper">
                <div class="bar" style="height: {height}%; background: {color};">
                    <span class="bar-value">{val}</span>
                </div>
                <div class="bar-label">{sev[0].upper()}</div>
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
                       scores_dir: Path,
                       benchmark_file: Optional[Path] = None,
                       output_file: Path = Path("report.html")) -> Path:
        """Generate beautiful HTML report from scoring results."""
        console.print("[cyan]Generating Enhanced ScaBench Report...[/cyan]")
        
        # Load all scoring results
        score_files = list(scores_dir.glob("score_*.json"))
        if not score_files:
            console.print(f"[red]No score files found in {scores_dir}[/red]")
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
        
        console.print(f"[green]✨ Beautiful report generated: {output_file}[/green]")
        return output_file
    
    def _generate_html(self, scores: List[Dict], stats: Dict, charts: Dict) -> str:
        """Generate the beautiful HTML content."""
        
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
                width: 120px;
                height: 120px;
            }
            
            .circle-bg {
                fill: none;
                stroke: #eee;
                stroke-width: 3.8;
            }
            
            .circle {
                fill: none;
                stroke: url(#gradient);
                stroke-width: 3.8;
                stroke-linecap: round;
                transform: rotate(-90deg);
                transform-origin: center;
                animation: progress 1s ease-out forwards;
            }
            
            .percentage {
                fill: var(--dark);
                font-size: 0.5em;
                text-anchor: middle;
                font-weight: 700;
            }
            
            .mini-bar-chart {
                display: flex;
                justify-content: space-around;
                align-items: flex-end;
                height: 120px;
                padding: 10px;
                gap: 10px;
            }
            
            .bar-wrapper {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: flex-end;
            }
            
            .bar {
                width: 100%;
                border-radius: 4px 4px 0 0;
                position: relative;
                transition: all 0.3s ease;
                display: flex;
                align-items: flex-start;
                justify-content: center;
                padding-top: 5px;
                animation: grow 0.8s ease-out;
            }
            
            .bar:hover {
                opacity: 0.8;
            }
            
            .bar-value {
                color: white;
                font-weight: 600;
                font-size: 0.875rem;
            }
            
            .bar-label {
                margin-top: 5px;
                font-size: 0.75rem;
                font-weight: 600;
                color: var(--dark);
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
                max-height: 0;
                overflow: hidden;
                transition: max-height 0.3s ease;
            }
            
            .project-card.expanded .project-details {
                max-height: 2000px;
            }
            
            .details-content {
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
                const card = element.closest('.project-card');
                card.classList.toggle('expanded');
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
            '<title>Security Tool Benchmark Report - ScaBench</title>',
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
            '<div class="nav-title">🎯 Security Benchmark</div>',
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
            '<h1>Security Tool Benchmark Report</h1>',
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
                    <div class="details-content">
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
                for match in score['matched_findings']:
                    severity = match.get('severity', 'unknown').lower()
                    html_parts.append(f'''
                    <div class="finding-card">
                        <div class="finding-header">
                            <div class="finding-title">
                                {match.get('expected', 'Unknown')}
                                <span class="confidence-indicator">100% Match</span>
                            </div>
                            <span class="severity-badge severity-{severity}">{severity}</span>
                        </div>
                        <div class="justification-box">
                            <strong>Justification:</strong> {match.get('justification', 'No justification provided')}
                        </div>
                    </div>
                    ''')
            else:
                html_parts.append('<p style="color: #6b7280; text-align: center; padding: 2rem;">No matched vulnerabilities</p>')
            html_parts.append('</div>')
            
            # Missed findings tab
            html_parts.append('<div class="tab-content" data-tab="missed">')
            if score['missed_findings']:
                for miss in score['missed_findings']:
                    severity = miss.get('severity', 'unknown').lower()
                    html_parts.append(f'''
                    <div class="finding-card">
                        <div class="finding-header">
                            <div class="finding-title">{miss.get('title', 'Unknown')}</div>
                            <span class="severity-badge severity-{severity}">{severity}</span>
                        </div>
                        <div class="justification-box">
                            <strong>Reason:</strong> {miss.get('reason', 'Not detected by tool')}
                        </div>
                    </div>
                    ''')
            else:
                html_parts.append('<p style="color: #6b7280; text-align: center; padding: 2rem;">No missed vulnerabilities</p>')
            html_parts.append('</div>')
            
            # Extra findings tab
            html_parts.append('<div class="tab-content" data-tab="extra">')
            if score['extra_findings']:
                for extra in score['extra_findings']:
                    severity = extra.get('severity', 'unknown').lower()
                    html_parts.append(f'''
                    <div class="finding-card">
                        <div class="finding-header">
                            <div class="finding-title">{extra.get('title', 'Unknown')}</div>
                            <span class="severity-badge severity-{severity}">{severity}</span>
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
    parser = argparse.ArgumentParser(description='Generate beautiful ScaBench HTML reports')
    parser.add_argument('--scores', required=True, help='Directory containing score JSON files')
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
    
    console.print("\n[bold green]Report successfully generated![/bold green]")
    console.print(f"View the report: {args.output}")


if __name__ == "__main__":
    main()