from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
import requests
import re
from io import BytesIO
import PyPDF2
import os
import json
from bs4 import BeautifulSoup

from base_scraper import BaseScraper
from scraper_factory import register_scraper
from models import Project, Codebase, Vulnerability

logger = logging.getLogger(__name__)


@register_scraper("sherlock")
class SherlockScraper(BaseScraper):
    
    GITHUB_API_URL = "https://api.github.com/repos/sherlock-protocol/sherlock-reports"
    GITHUB_RAW_URL = "https://raw.githubusercontent.com/sherlock-protocol/sherlock-reports/main"
    AUDITS_PATH = "/audits"
    
    def __init__(self, platform: str = "sherlock", test_mode: bool = False, test_data_dir: str = None):
        super().__init__(platform, test_mode, test_data_dir)
    
    def fetch_contests(self, period_start: datetime, period_end: datetime) -> List[Dict[str, Any]]:
        self.logger.info(f"Fetching Sherlock contests from {period_start} to {period_end}")
        contests = []
        
        try:
            api_url = f"{self.GITHUB_API_URL}/contents/audits"
            response = requests.get(api_url, timeout=30)
            response.raise_for_status()
            
            files = response.json()
            
            for file in files:
                if file['name'].endswith('.pdf'):
                    contest_info = self._parse_filename(file['name'])
                    if contest_info:
                        contest_date = contest_info.get('date')
                        if contest_date and period_start <= contest_date <= period_end:
                            contests.append({
                                'id': file['name'].replace('.pdf', ''),
                                'name': contest_info.get('name', file['name']),
                                'date': contest_date,
                                'pdf_url': file['download_url']
                            })
            
            self.logger.info(f"Found {len(contests)} Sherlock contests in date range")
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch Sherlock repository contents: {e}")
        except Exception as e:
            self.logger.error(f"Error parsing Sherlock contests: {e}")
        
        return contests
    
    def fetch_report(self, contest_id: str) -> Optional[Dict[str, Any]]:
        self.logger.info(f"Fetching Sherlock report for contest: {contest_id}")
        
        try:
            if self.test_mode and self.test_data_dir:
                # Load from local test data  
                test_file = os.path.join(self.test_data_dir, 'sherlock-metalend.pdf')
                if os.path.exists(test_file):
                    with open(test_file, 'rb') as f:
                        pdf_content = BytesIO(f.read())
                else:
                    self.logger.error(f"Test PDF file not found: {test_file}")
                    return None
            else:
                pdf_url = f"{self.GITHUB_RAW_URL}/audits/{contest_id}.pdf"
                response = requests.get(pdf_url, timeout=60)
                response.raise_for_status()
                pdf_content = BytesIO(response.content)
            
            project = self._parse_pdf_report(pdf_content, contest_id)
            
            if project:
                return project.to_dict()
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch PDF for {contest_id}: {e}")
        except Exception as e:
            self.logger.error(f"Error parsing PDF for {contest_id}: {e}")
        
        return None
    
    def _parse_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        date_pattern = r'(\d{4})[-_](\d{2})[-_](\d{2})'
        match = re.search(date_pattern, filename)
        
        if match:
            year, month, day = match.groups()
            contest_date = datetime(int(year), int(month), int(day))
            
            name = filename.replace('.pdf', '')
            name = re.sub(date_pattern, '', name)
            name = name.strip('-_')
            
            return {
                'name': name or 'Unknown',
                'date': contest_date
            }
        
        return None
    
    def _parse_pdf_report(self, pdf_content: BytesIO, contest_id: str) -> Optional[Project]:
        self.logger.info(f"Parsing PDF report for {contest_id}")
        
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_content)
            full_text = ""
            
            # Extract text from all pages
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                full_text += page_text + "\n"
            
            # Extract project information
            project_name = self._extract_project_name(full_text) or contest_id
            contest_date = self._extract_date_from_filename(contest_id) or datetime.now()
            
            project_id = self.normalize_project_id(project_name, contest_date)
            
            project = Project(
                project_id=project_id,
                name=project_name,
                platform=self.platform,
                contest_date=contest_date,
                report_url=f"{self.GITHUB_RAW_URL}/audits/{contest_id}.pdf"
            )
            
            # Extract GitHub information
            github_info = self._extract_github_from_text(full_text)
            if github_info:
                repo_url, commit = github_info
                codebase = Codebase(
                    codebase_id=self.normalize_codebase_id(project_name, commit or "unknown"),
                    repo_url=repo_url,
                    commit=commit or "",
                    tree_url=self.create_tree_url(repo_url, commit) if commit else "",
                    tarball_url=self.create_tarball_url(repo_url, commit) if commit else ""
                )
                project.codebases.append(codebase)
            
            # Extract vulnerabilities from the PDF
            vulnerabilities = self._extract_vulnerabilities_from_pdf(full_text, contest_id)
            project.vulnerabilities.extend(vulnerabilities)
            
            self.logger.info(f"Parsed Sherlock report: {project_name} with {len(vulnerabilities)} findings")
            
            return project
            
        except Exception as e:
            self.logger.error(f"Error reading PDF: {e}")
            return None
    
    def _extract_project_name(self, text: str) -> Optional[str]:
        # Look for "MetaLend" or similar project names in the first part of the PDF
        lines = text.split('\n')
        
        # Try to find the project name in various patterns
        for i, line in enumerate(lines[:50]):
            # Look for lines that contain "Audit Report" or "Security Audit"
            if 'Audit Report' in line or 'Security Audit' in line:
                # The project name is usually before these terms
                if i > 0:
                    potential_name = lines[i-1].strip()
                    if potential_name and len(potential_name) > 2 and len(potential_name) < 50:
                        return potential_name
                    
                # Or it might be in the same line
                name_match = re.search(r'^([\w\s]+?)\s*(?:Audit|Security)', line)
                if name_match:
                    return name_match.group(1).strip()
            
            # Look for standalone project names (often in larger font, appearing alone)
            if line.strip() and len(line.strip()) > 3 and len(line.strip()) < 30:
                # Avoid dates and common headers
                if not re.match(r'^\d{4}', line) and 'Table of Contents' not in line:
                    if not any(skip in line.lower() for skip in ['summary', 'introduction', 'scope', 'findings']):
                        # This might be the project name
                        return line.strip()
        
        return None
    
    def _extract_date_from_filename(self, filename: str) -> Optional[datetime]:
        """Extract date from filename like '2024.03.27 - Final - MetaLend Audit Report'"""
        # Pattern: YYYY.MM.DD
        date_pattern = r'(\d{4})\.(\d{2})\.(\d{2})'
        match = re.search(date_pattern, filename)
        
        if match:
            year, month, day = match.groups()
            try:
                return datetime(int(year), int(month), int(day))
            except ValueError:
                pass
        
        return None
    
    def _extract_vulnerabilities_from_pdf(self, text: str, contest_id: str) -> List[Vulnerability]:
        """Extract vulnerability findings from Sherlock PDF report"""
        vulnerabilities = []
        
        try:
            # Common patterns in Sherlock reports
            # Pattern 1: "High Risk: [Title]"
            # Pattern 2: "Medium Risk: [Title]"
            # Pattern 3: "H-01: [Title]", "M-01: [Title]"
            # Pattern 4: "Issue #1: [Title] (High/Medium/Low)"
            
            # Track finding counts
            finding_counts = {'high': 0, 'medium': 0, 'low': 0}
            
            # Split text into lines for easier processing
            lines = text.split('\n')
            
            # Pattern 1: Look for severity markers followed by titles
            severity_patterns = [
                (r'High\s+(?:Risk|Severity)[:\s]+(.+)', 'high'),
                (r'Medium\s+(?:Risk|Severity)[:\s]+(.+)', 'medium'),
                (r'Low\s+(?:Risk|Severity)[:\s]+(.+)', 'low'),
                (r'Critical\s+(?:Risk|Severity)[:\s]+(.+)', 'critical')
            ]
            
            for pattern, severity in severity_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    title = match.group(1).strip()
                    if title and len(title) > 5 and len(title) < 200:
                        finding_counts[severity] += 1
                        finding_id = f"{contest_id}_{severity[0].upper()}-{finding_counts[severity]:02d}"
                        
                        vuln = Vulnerability(
                            finding_id=finding_id,
                            severity=severity,
                            title=title,
                            description=""
                        )
                        vulnerabilities.append(vuln)
            
            # Pattern 2: Look for H-01, M-01, L-01 style findings
            finding_patterns = [
                (r'H-(\d+)[:\s]+(.+?)(?=\n|$)', 'high'),
                (r'M-(\d+)[:\s]+(.+?)(?=\n|$)', 'medium'),
                (r'L-(\d+)[:\s]+(.+?)(?=\n|$)', 'low')
            ]
            
            for pattern, severity in finding_patterns:
                matches = re.finditer(pattern, text, re.MULTILINE)
                for match in matches:
                    finding_num = match.group(1)
                    title = match.group(2).strip()
                    
                    if title and len(title) > 5:
                        # Clean up title
                        title = re.sub(r'\s+', ' ', title)  # Normalize whitespace
                        title = title[:200]  # Limit length
                        
                        finding_id = f"{contest_id}_{severity[0].upper()}-{finding_num.zfill(2)}"
                        
                        # Check if we already have this finding
                        if not any(v.finding_id == finding_id for v in vulnerabilities):
                            vuln = Vulnerability(
                                finding_id=finding_id,
                                severity=severity,
                                title=title,
                                description=""
                            )
                            vulnerabilities.append(vuln)
            
            # Pattern 3: Look for "Issue #X:" patterns
            issue_pattern = r'Issue\s+#(\d+)[:\s]+(.+?)\s*\(([Hh]igh|[Mm]edium|[Ll]ow|[Cc]ritical)\)'
            matches = re.finditer(issue_pattern, text, re.MULTILINE)
            
            for match in matches:
                issue_num = match.group(1)
                title = match.group(2).strip()
                severity = match.group(3).lower()
                
                if title and len(title) > 5:
                    finding_id = f"{contest_id}_Issue-{issue_num.zfill(2)}"
                    
                    if not any(v.finding_id == finding_id for v in vulnerabilities):
                        vuln = Vulnerability(
                            finding_id=finding_id,
                            severity=severity,
                            title=title,
                            description=""
                        )
                        vulnerabilities.append(vuln)
            
            # If no vulnerabilities found with patterns, try a more general approach
            if not vulnerabilities:
                # Look for sections that indicate findings
                finding_sections = re.finditer(
                    r'(Finding|Issue|Vulnerability)\s+(\d+)[:\s]+(.+?)(?=Finding|Issue|Vulnerability|\n\n|$)',
                    text,
                    re.IGNORECASE | re.DOTALL
                )
                
                for match in finding_sections:
                    finding_num = match.group(2)
                    content = match.group(3)[:500]  # Get first 500 chars
                    
                    # Try to extract title from content
                    title_match = re.match(r'^([^\n]{10,150})', content)
                    if title_match:
                        title = title_match.group(1).strip()
                        
                        # Try to determine severity from content
                        severity = 'medium'  # Default
                        if re.search(r'\b(high|critical)\b', content, re.IGNORECASE):
                            severity = 'high'
                        elif re.search(r'\blow\b', content, re.IGNORECASE):
                            severity = 'low'
                        
                        finding_id = f"{contest_id}_Finding-{finding_num.zfill(2)}"
                        
                        vuln = Vulnerability(
                            finding_id=finding_id,
                            severity=severity,
                            title=title,
                            description=""
                        )
                        vulnerabilities.append(vuln)
            
            # Remove duplicates based on title similarity
            unique_vulnerabilities = []
            seen_titles = set()
            
            for vuln in vulnerabilities:
                # Normalize title for comparison
                normalized = vuln.title.lower().strip()
                normalized = re.sub(r'\s+', ' ', normalized)
                
                if normalized not in seen_titles:
                    seen_titles.add(normalized)
                    unique_vulnerabilities.append(vuln)
            
            self.logger.info(
                f"Extracted {len(unique_vulnerabilities)} vulnerabilities from Sherlock PDF: "
                f"High={sum(1 for v in unique_vulnerabilities if v.severity == 'high')}, "
                f"Medium={sum(1 for v in unique_vulnerabilities if v.severity == 'medium')}, "
                f"Low={sum(1 for v in unique_vulnerabilities if v.severity == 'low')}"
            )
            
            return unique_vulnerabilities
            
        except Exception as e:
            self.logger.error(f"Error extracting vulnerabilities from PDF: {e}")
            return []
    
    def _extract_github_from_text(self, text: str) -> Optional[tuple]:
        github_pattern = r'https://github\.com/[^\s]+'
        matches = re.findall(github_pattern, text)
        
        if matches:
            repo_url = matches[0].rstrip('.,;)')
            
            commit_pattern = r'\b[0-9a-f]{40}\b|\b[0-9a-f]{7,10}\b'
            commit_match = re.search(commit_pattern, text)
            commit = commit_match.group(0) if commit_match else None
            
            return repo_url, commit
        
        return None