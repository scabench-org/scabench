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
            if self.test_mode and self.test_data_dir:
                # Load from local test data
                test_file = os.path.join(self.test_data_dir, 'sherlock-audits.html')
                with open(test_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Parse the HTML to extract file list
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Look for the embedded JSON data
                script_tag = soup.find('script', {'type': 'application/json', 'data-target': 'react-app.embeddedData'})
                if script_tag:
                    import json
                    data = json.loads(script_tag.string)
                    files = data.get('payload', {}).get('tree', {}).get('items', [])
                else:
                    files = []
            else:
                api_url = f"{self.GITHUB_API_URL}/contents/audits"
                response = requests.get(api_url, timeout=30)
                response.raise_for_status()
                
                files = response.json()
            
            for file in files:
                # Handle both test mode (dict with 'name' key) and API mode (dict with 'name' key)
                filename = file.get('name', '') if isinstance(file, dict) else str(file)
                
                if filename.endswith('.pdf'):
                    contest_info = self._parse_filename(filename)
                    if contest_info:
                        contest_date = contest_info.get('date')
                        if contest_date and period_start <= contest_date <= period_end:
                            contests.append({
                                'id': filename.replace('.pdf', ''),
                                'name': contest_info.get('name', filename),
                                'date': contest_date,
                                'pdf_url': file.get('download_url', '') if isinstance(file, dict) else f"{self.GITHUB_RAW_URL}/audits/{filename}"
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
        # Date pattern: YYYY.MM.DD or YYYY.DD.MM (some files have day-month swapped)
        date_pattern = r'(\d{4})\.(\d{1,2})\.(\d{1,2})'
        match = re.search(date_pattern, filename)
        
        if match:
            year, first_num, second_num = match.groups()
            year = int(year)
            first_num = int(first_num)
            second_num = int(second_num)
            
            # Try to determine if it's MM.DD or DD.MM format
            # Most files seem to use YYYY.MM.DD format
            if first_num <= 12:
                month = first_num
                day = second_num
            else:
                # If first number > 12, it must be day
                month = second_num
                day = first_num
            
            # Handle edge cases where day might be invalid
            try:
                contest_date = datetime(year, month, day)
            except ValueError:
                # Try swapping month and day
                try:
                    contest_date = datetime(year, day, month)
                except ValueError:
                    self.logger.warning(f"Could not parse date from filename: {filename}")
                    return None
            
            # Extract name by removing date and .pdf
            name = filename.replace('.pdf', '')
            name = re.sub(date_pattern + r'\s*-?\s*', '', name)
            name = name.strip('- ')
            
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
                
                # Fix common PDF extraction issues with missing spaces
                page_text = self._fix_pdf_spacing(page_text)
                
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
            # Sherlock reports typically have issues in format:
            # "Issue H-1: [Title]" or "Issue M-01: [Title]" etc.
            # followed by Source URL and complete vulnerability details
            
            # Pattern to find issues with their COMPLETE content
            issue_pattern = r'Issue\s+([HMLhml])-?(\d+)[:\s]+(.+?)(?=Issue\s+[HMLhml]-?\d+|$)'
            matches = re.finditer(issue_pattern, text, re.DOTALL)
            
            for match in matches:
                severity_letter = match.group(1).upper()
                issue_num = match.group(2)
                content = match.group(3)
                
                # Map letter to severity
                severity_map = {'H': 'high', 'M': 'medium', 'L': 'low'}
                severity = severity_map.get(severity_letter, 'medium')
                
                # Extract title (first line of content)
                lines = content.split('\n')
                title = lines[0].strip()
                
                # Build complete description with ALL sections
                description_parts = []
                
                # Extract source URL if present
                source_match = re.search(r'Source:\s*(https?://[^\s]+)', content)
                if source_match:
                    description_parts.append(f"Source: {source_match.group(1)}")
                    description_parts.append("")  # Add blank line
                
                # Extract all main sections
                sections_to_extract = [
                    ('Summary', r'Summary\s*\n(.+?)(?=\n(?:Vulnerability Detail|Impact|Code Snippet|Tool Used|Recommendation|Discussion|Resolution|$))'),
                    ('Vulnerability Detail', r'Vulnerability Detail\s*\n(.+?)(?=\n(?:Impact|Code Snippet|Tool Used|Recommendation|Discussion|Resolution|$))'),
                    ('Impact', r'Impact\s*\n(.+?)(?=\n(?:Code Snippet|Tool Used|Recommendation|Discussion|Resolution|$))'),
                    ('Proof of Concept', r'(?:Proof of Concept|PoC)\s*\n(.+?)(?=\n(?:Code Snippet|Tool Used|Recommendation|Discussion|Resolution|$))'),
                    ('Code Snippet', r'Code Snippet\s*\n(.+?)(?=\n(?:Tool Used|Recommendation|Discussion|Resolution|$))'),
                    ('Tool Used', r'Tool Used\s*\n(.+?)(?=\n(?:Recommendation|Discussion|Resolution|$))'),
                    ('Recommendation', r'Recommendation\s*\n(.+?)(?=\n(?:Discussion|Resolution|$))')
                ]
                
                for section_name, pattern in sections_to_extract:
                    section_match = re.search(pattern, content, re.DOTALL)
                    if section_match:
                        section_text = section_match.group(1).strip()
                        
                        # Clean up excessive whitespace but preserve code formatting
                        if section_name in ['Code Snippet', 'Proof of Concept']:
                            # For code sections, preserve some formatting but fix spacing
                            # Don't normalize all whitespace, just clean up excessive newlines
                            section_text = re.sub(r'\n{3,}', '\n\n', section_text)
                        else:
                            # For text sections, normalize whitespace more aggressively
                            # This will help with readability but might lose some formatting
                            section_text = re.sub(r'\s+', ' ', section_text)
                        
                        if section_text:
                            description_parts.append(f"**{section_name}:**")
                            description_parts.append(section_text)
                            description_parts.append("")  # Add blank line between sections
                
                # If we couldn't extract structured sections, fall back to getting all content
                if len(description_parts) <= 2:  # Only source URL or nothing
                    # Clean and include all content after the title
                    all_content = '\n'.join(lines[1:])
                    all_content = re.sub(r'\n{3,}', '\n\n', all_content)
                    description_parts.append(all_content)
                
                # Join all parts into complete description
                description = '\n'.join(description_parts)
                
                # Don't limit the description length - we want COMPLETE information
                # Only clean up trailing whitespace
                description = description.strip()
                
                finding_id = f"{contest_id}_{severity_letter}-{issue_num.zfill(2)}"
                
                vuln = Vulnerability(
                    finding_id=finding_id,
                    severity=severity,
                    title=title[:500],  # Reasonable title length limit
                    description=description  # COMPLETE description, no truncation
                )
                vulnerabilities.append(vuln)
            
            # If no issues found with "Issue" pattern, try other patterns
            if not vulnerabilities:
                # Pattern 2: Look for H-01, M-01, L-01 style findings
                finding_patterns = [
                    (r'([HML])-(\d+)[:\s]+(.+?)(?=(?:[HML]-\d+|Source:|$))', None)
                ]
                
                for pattern, _ in finding_patterns:
                    matches = re.finditer(pattern, text, re.DOTALL)
                    for match in matches:
                        severity_letter = match.group(1).upper()
                        finding_num = match.group(2)
                        content = match.group(3)
                        
                        # Map letter to severity
                        severity_map = {'H': 'high', 'M': 'medium', 'L': 'low'}
                        severity = severity_map.get(severity_letter, 'medium')
                        
                        # Extract title (first line)
                        lines = content.split('\n')
                        title = lines[0].strip()
                        
                        if title and len(title) > 5:
                            # Clean up title
                            title = re.sub(r'\s+', ' ', title)[:200]
                            
                            # Extract source URL from content
                            source_url = ""
                            source_match = re.search(r'Source:\s*(https?://[^\s]+)', content)
                            if source_match:
                                source_url = f"Source: {source_match.group(1)}"
                            
                            # Get description from rest of content
                            description_text = ' '.join(lines[1:10])  # Get next few lines
                            description_text = re.sub(r'\s+', ' ', description_text)[:300]
                            
                            description = f"{source_url} {description_text}".strip()[:500]
                            
                            finding_id = f"{contest_id}_{severity_letter}-{finding_num.zfill(2)}"
                            
                            # Check if we already have this finding
                            if not any(v.finding_id == finding_id for v in vulnerabilities):
                                vuln = Vulnerability(
                                    finding_id=finding_id,
                                    severity=severity,
                                    title=title,
                                    description=description
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
    
    def _fix_pdf_spacing(self, text: str) -> str:
        """Fix common PDF text extraction issues with missing spaces"""
        
        # Fix missing spaces between words
        # Add space before capital letters that follow lowercase letters (camelCase -> camel Case)
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        
        # Fix specific patterns where words are commonly concatenated
        # Add space between letter and number combinations
        text = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', text)
        text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', text)
        
        # Fix common concatenations in technical text
        # Add space after punctuation if missing
        text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
        text = re.sub(r'([,;:])([A-Za-z])', r'\1 \2', text)
        
        # Fix specific patterns seen in Sherlock PDFs
        # Common word boundaries that get concatenated
        patterns_to_fix = [
            (r'function([A-Z])', r'function \1'),
            (r'contract([A-Z])', r'contract \1'),
            (r'address([A-Z])', r'address \1'),
            (r'uint256([A-Z])', r'uint256 \1'),
            (r'memory([A-Z])', r'memory \1'),
            (r'storage([A-Z])', r'storage \1'),
            (r'returns([A-Z])', r'returns \1'),
            (r'require([A-Z])', r'require \1'),
            (r'revert([A-Z])', r'revert \1'),
            (r'modifier([A-Z])', r'modifier \1'),
            (r'mapping([A-Z])', r'mapping \1'),
            (r'event([A-Z])', r'event \1'),
            (r'struct([A-Z])', r'struct \1'),
            (r'interface([A-Z])', r'interface \1'),
            (r'library([A-Z])', r'library \1'),
        ]
        
        for pattern, replacement in patterns_to_fix:
            text = re.sub(pattern, replacement, text)
        
        # Fix multiple spaces (clean up after additions)
        text = re.sub(r' +', ' ', text)
        
        # Fix spacing around brackets and parentheses in code
        text = re.sub(r'(\w)\(', r'\1 (', text)
        text = re.sub(r'\)(\w)', r') \1', text)
        
        return text
    
    def _extract_finding_description_from_text(self, text: str, title: str) -> str:
        """Extract description text that follows a finding title in the PDF"""
        try:
            # Find the position of the title in the text
            title_pos = text.find(title)
            if title_pos == -1:
                return ""
            
            # Get text after the title
            after_title = text[title_pos + len(title):title_pos + len(title) + 2000]  # Get next 2000 chars
            
            # Split into lines
            lines = after_title.split('\n')
            
            description_lines = []
            for line in lines[1:10]:  # Look at next 10 lines after title
                line = line.strip()
                
                # Stop if we hit another finding or section header
                if any(marker in line for marker in ['H-', 'M-', 'L-', 'High Risk', 'Medium Risk', 'Low Risk', 'Finding', 'Issue #']):
                    break
                
                # Skip empty lines and very short lines
                if len(line) > 10:
                    # Skip lines that look like headers or metadata
                    if not any(skip in line.lower() for skip in ['severity:', 'impact:', 'likelihood:', 'submitted by', 'status:']):
                        description_lines.append(line)
                        
                        # Stop after getting a reasonable description
                        if len(' '.join(description_lines)) > 100:
                            break
            
            description = ' '.join(description_lines)[:500]  # Limit to 500 chars
            
            # Clean up the description
            description = re.sub(r'\s+', ' ', description)  # Normalize whitespace
            description = description.strip()
            
            return description
            
        except Exception as e:
            self.logger.debug(f"Error extracting description: {e}")
            return ""
    
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