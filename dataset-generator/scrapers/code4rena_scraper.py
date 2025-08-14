from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
import requests
from bs4 import BeautifulSoup
import re
import json
import os

from base_scraper import BaseScraper
from scraper_factory import register_scraper
from models import Project, Codebase, Vulnerability

logger = logging.getLogger(__name__)


@register_scraper("code4rena")
class Code4renaScraper(BaseScraper):
    
    BASE_URL = "https://code4rena.com"
    REPORTS_URL = f"{BASE_URL}/reports"
    
    def __init__(self, platform: str = "code4rena", test_mode: bool = False, test_data_dir: str = None):
        super().__init__(platform, test_mode, test_data_dir)
    
    def fetch_contests(self, period_start: datetime, period_end: datetime) -> List[Dict[str, Any]]:
        self.logger.info(f"Fetching Code4rena contests from {period_start} to {period_end}")
        contests = []
        
        try:
            if self.test_mode and self.test_data_dir:
                # Load from local test data
                test_file = os.path.join(self.test_data_dir, 'codearena-reports.html')
                with open(test_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            else:
                response = requests.get(self.REPORTS_URL, timeout=30)
                response.raise_for_status()
                html_content = response.text
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract JSON data from the HTML (it's embedded with escaped quotes)
            # The data is in the HTML, not necessarily in script tags with .string attribute
            contests_data = self._extract_contests_from_script(html_content, period_start, period_end)
            contests.extend(contests_data)
            
            self.logger.info(f"Found {len(contests)} Code4rena contests in date range")
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch Code4rena reports page: {e}")
        except Exception as e:
            self.logger.error(f"Error parsing Code4rena contests: {e}")
        
        return contests
    
    def fetch_report(self, contest_id: str) -> Optional[Dict[str, Any]]:
        self.logger.info(f"Fetching Code4rena report for contest: {contest_id}")
        
        try:
            if self.test_mode and self.test_data_dir:
                # Try to load from local test data
                test_file = os.path.join(self.test_data_dir, f'codearena-{contest_id}.html')
                if os.path.exists(test_file):
                    with open(test_file, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                else:
                    # Use sample report if specific one not found
                    test_file = os.path.join(self.test_data_dir, 'codearena-2025-04-virtuals-protocol.html')
                    with open(test_file, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                report_url = f"{self.BASE_URL}/reports/{contest_id}"
            else:
                report_url = f"{self.BASE_URL}/reports/{contest_id}"
                response = requests.get(report_url, timeout=30)
                response.raise_for_status()
                html_content = response.text
            
            soup = BeautifulSoup(html_content, 'html.parser')
            project = self._parse_report(soup, contest_id, report_url)
            
            if project:
                return project.to_dict()
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch report for {contest_id}: {e}")
        except Exception as e:
            self.logger.error(f"Error parsing report for {contest_id}: {e}")
        
        return None
    
    def _parse_report(self, soup: BeautifulSoup, contest_id: str, report_url: str) -> Optional[Project]:
        try:
            # Extract project name from title
            title_elem = soup.find('h1')
            project_name = "Unknown Project"
            if title_elem:
                # Clean up the title text
                title_text = title_elem.get_text(strip=True)
                # Remove "Findings & Analysis Report" suffix if present
                project_name = title_text.replace('Findings & Analysis Report', '').replace('Findings &amp; Analysis Report', '').strip()
            
            # Extract date
            date_elem = soup.find('h4')
            contest_date = datetime.now()
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                try:
                    contest_date = datetime.strptime(date_text, '%Y-%m-%d')
                except:
                    try:
                        contest_date = datetime.strptime(date_text, '%Y-%B-%d')
                    except:
                        pass
            
            project_id = self.normalize_project_id(project_name, contest_date)
            
            project = Project(
                project_id=project_id,
                name=project_name,
                platform=self.platform,
                contest_date=contest_date,
                report_url=report_url
            )
            
            # Extract GitHub URLs from the report
            github_urls = self._extract_github_urls(soup)
            for url in github_urls:
                repo_url, commit = self._parse_github_url(url)
                if repo_url:
                    codebase = Codebase(
                        codebase_id=self.normalize_codebase_id(project_name, commit or "main"),
                        repo_url=repo_url,
                        commit=commit or "",
                        tree_url=self.create_tree_url(repo_url, commit) if commit else "",
                        tarball_url=self.create_tarball_url(repo_url, commit) if commit else ""
                    )
                    if not any(cb.repo_url == repo_url for cb in project.codebases):
                        project.codebases.append(codebase)
            
            # Extract vulnerabilities
            vulnerabilities = self._extract_vulnerabilities(soup, contest_id)
            project.vulnerabilities.extend(vulnerabilities)
            
            return project
            
        except Exception as e:
            self.logger.error(f"Error parsing report for {contest_id}: {e}")
            return None
    
    def _extract_github_info(self, text: str) -> Optional[tuple]:
        github_pattern = r'https://github\.com/([^/]+)/([^/\s]+)'
        match = re.search(github_pattern, text)
        if match:
            return match.group(0), match.group(1), match.group(2)
        return None
    
    def _extract_commit_hash(self, text: str) -> Optional[str]:
        commit_pattern = r'\b[0-9a-f]{40}\b'
        match = re.search(commit_pattern, text)
        if match:
            return match.group(0)
        
        short_commit_pattern = r'\b[0-9a-f]{7,10}\b'
        match = re.search(short_commit_pattern, text)
        if match:
            return match.group(0)
        
        return None
    
    def _extract_contests_from_script(self, script_text: str, period_start: datetime, period_end: datetime) -> List[Dict[str, Any]]:
        """Extract contest data from JavaScript embedded in HTML"""
        contests = []
        seen_slugs = set()  # Track unique slugs to avoid duplicates
        
        # Pattern to find contest objects with escaped quotes in HTML
        # Looking for patterns like: {\"alt_url\":...,\"date\":\"2023-07-26\",\"slug\":\"2023-05-juicebox\"...}
        pattern = r'\{[^}]*\\"date\\":\\"(\d{4}-\d{2}-\d{2})\\"[^}]*\\"slug\\":\\"([^\\]+)\\"[^}]*\}'
        matches = re.finditer(pattern, script_text)
        
        for match in matches:
            report_date_str = match.group(1)
            slug = match.group(2)
            
            # Skip if we've already seen this slug
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            
            # Extract contest date from slug (e.g., "2023-05-juicebox" -> "2023-05")
            slug_date_match = re.match(r'(\d{4})-(\d{2})', slug)
            if slug_date_match:
                year = int(slug_date_match.group(1))
                month = int(slug_date_match.group(2))
                
                # Create contest date from slug (use first day of month)
                try:
                    contest_date = datetime(year, month, 1)
                    if period_start <= contest_date <= period_end:
                        contests.append({
                            'id': slug,
                            'date': contest_date,
                            'report_date': report_date_str,
                            'url': f"{self.BASE_URL}/reports/{slug}"
                        })
                except Exception as e:
                    self.logger.debug(f"Failed to parse contest date from slug {slug}: {e}")
        
        return contests
    
    def _extract_github_urls(self, soup: BeautifulSoup) -> List[str]:
        """Extract GitHub URLs from the report HTML"""
        urls = set()
        
        # Find all links that contain github.com
        for link in soup.find_all('a', href=re.compile(r'github\.com')):
            href = link.get('href', '')
            if href:
                urls.add(href)
        
        # Also search in text for GitHub URLs
        text = soup.get_text()
        github_pattern = r'https://github\.com/[^\s<>"]+'
        matches = re.findall(github_pattern, text)
        urls.update(matches)
        
        return list(urls)
    
    def _parse_github_url(self, url: str) -> tuple:
        """Parse GitHub URL to extract repo URL and commit hash"""
        # Clean up URL
        url = url.rstrip('.,;)\'"')
        
        # Check if it's a blob/tree URL with commit
        if '/blob/' in url or '/tree/' in url:
            parts = url.split('/')
            if len(parts) >= 7:
                org = parts[3]
                repo = parts[4]
                commit = parts[6]
                repo_url = f"https://github.com/{org}/{repo}"
                return repo_url, commit
        
        # Check if it's a regular repo URL
        match = re.match(r'https://github\.com/([^/]+)/([^/\s]+)', url)
        if match:
            repo_url = match.group(0).rstrip('/')
            return repo_url, None
        
        return None, None
    
    def _extract_vulnerabilities(self, soup: BeautifulSoup, contest_id: str) -> List[Vulnerability]:
        """Extract vulnerability findings from the report"""
        vulnerabilities = []
        
        # Build a map of vulnerability IDs to their full content sections
        vuln_content_map = {}
        numbered_issues = {}  # Track numbered issues separately
        
        # Find all headers with vulnerability IDs
        for header in soup.find_all(['h2', 'h3', 'h4']):
            header_text = header.get_text(strip=True)
            
            # Match patterns like [H-01], [M-01], [L-01] in the header
            match = re.search(r'\[([HML])-(\d+)\]', header_text)
            if match:
                severity_letter = match.group(1)
                finding_num = match.group(2)
                finding_key = f"{severity_letter}-{finding_num.zfill(2)}"
                
                # Extract title - remove the ID prefix
                title = re.sub(r'^\[[HML]-\d+\]\s*', '', header_text).strip()
                
                # Extract the content following this header until the next similar header
                content_parts = []
                current = header.find_next_sibling()
                
                while current:
                    # Stop if we hit another vulnerability header
                    if current.name in ['h1', 'h2', 'h3', 'h4']:
                        current_text = current.get_text(strip=True)
                        if re.search(r'\[([HML])-\d+\]|\[\d+\]', current_text):
                            break
                    
                    # Collect text content
                    if current.name in ['p', 'pre', 'ul', 'ol', 'blockquote']:
                        text = current.get_text(separator='\n', strip=True)
                        if text:
                            content_parts.append(text)
                    
                    current = current.find_next_sibling()
                
                # Join the content parts
                description = '\n\n'.join(content_parts)
                
                # Map severity letter to full severity name
                severity_map = {'H': 'high', 'M': 'medium', 'L': 'low'}
                severity = severity_map.get(severity_letter, 'medium')
                
                vuln_content_map[finding_key] = {
                    'title': title,
                    'description': description,
                    'severity': severity
                }
            else:
                # Check for numbered format [01], [02], etc.
                match = re.search(r'\[(\d+)\]', header_text)
                if match:
                    finding_num = match.group(1)
                    finding_key = f"NC-{finding_num.zfill(2)}"  # Mark as non-critical initially
                    
                    # Extract title - remove the ID prefix
                    title = re.sub(r'^\[\d+\]\s*', '', header_text).strip()
                    
                    # Extract the content following this header until the next similar header
                    content_parts = []
                    current = header.find_next_sibling()
                    
                    while current:
                        # Stop if we hit another vulnerability header
                        if current.name in ['h1', 'h2', 'h3', 'h4']:
                            current_text = current.get_text(strip=True)
                            if re.search(r'\[([HML])-\d+\]|\[\d+\]', current_text):
                                break
                        
                        # Collect text content
                        if current.name in ['p', 'pre', 'ul', 'ol', 'blockquote']:
                            text = current.get_text(separator='\n', strip=True)
                            if text:
                                content_parts.append(text)
                        
                        current = current.find_next_sibling()
                    
                    # Join the content parts
                    description = '\n\n'.join(content_parts)
                    
                    numbered_issues[finding_key] = {
                        'title': title,
                        'description': description,
                        'severity': 'low'  # Will be low if these are the only issues
                    }
        
        # If we found NO H/M/L vulnerabilities but we have numbered issues,
        # treat the numbered issues as the main vulnerabilities (like in Upside contest)
        if not vuln_content_map and numbered_issues:
            # Check if this looks like a contest with only low-risk issues
            # by looking for "Low Risk and Non-Critical Issues" header
            low_risk_header = None
            for header in soup.find_all(['h1', 'h2']):
                header_text = header.get_text(strip=True)
                if 'Low Risk and Non-Critical Issues' in header_text:
                    low_risk_header = header
                    break
            
            if low_risk_header:
                # These numbered issues are the main vulnerabilities
                for key, issue in numbered_issues.items():
                    # Rename key from NC-XX to L-XX
                    new_key = key.replace('NC-', 'L-')
                    vuln_content_map[new_key] = issue
        
        # If we found vulnerabilities with content, use them
        if vuln_content_map:
            for finding_key, content in vuln_content_map.items():
                finding_id = f"{contest_id}_{finding_key}"
                
                vuln = Vulnerability(
                    finding_id=finding_id,
                    severity=content['severity'],
                    title=content['title'],
                    description=content['description']
                )
                vulnerabilities.append(vuln)
        else:
            # Fallback to the original method for extracting just titles
            for severity_level in ['high', 'medium', 'low']:
                headers = soup.find_all(['h2', 'h3'], string=re.compile(f'{severity_level}\s+risk', re.IGNORECASE))
                
                for header in headers:
                    current = header.find_next_sibling()
                    vuln_index = 1
                    
                    while current and current.name not in ['h1', 'h2']:
                        if current.name == 'ul':
                            for li in current.find_all('li'):
                                link = li.find('a')
                                if link:
                                    title = link.get_text(strip=True)
                                    title = re.sub(r'^\[[HML]-\d+\]\s*', '', title)
                                    
                                    finding_id = f"{contest_id}_{severity_level[0].upper()}-{vuln_index:02d}"
                                    
                                    # Try to find the corresponding section for description
                                    href = link.get('href', '')
                                    description = ""
                                    if href and href.startswith('#'):
                                        # Find the section with this ID
                                        section_id = href[1:]  # Remove the #
                                        section = soup.find(id=section_id)
                                        if section:
                                            # Extract content after this section
                                            content_parts = []
                                            current_desc = section.find_next_sibling()
                                            
                                            while current_desc:
                                                if current_desc.name in ['h1', 'h2', 'h3', 'h4']:
                                                    if re.search(r'\[([HML])-\d+\]', current_desc.get_text(strip=True)):
                                                        break
                                                
                                                if current_desc.name in ['p', 'pre', 'ul', 'ol', 'blockquote']:
                                                    text = current_desc.get_text(separator='\n', strip=True)
                                                    if text:
                                                        content_parts.append(text)
                                                
                                                current_desc = current_desc.find_next_sibling()
                                            
                                            description = '\n\n'.join(content_parts)
                                    
                                    vuln = Vulnerability(
                                        finding_id=finding_id,
                                        severity=severity_level,
                                        title=title,
                                        description=description
                                    )
                                    vulnerabilities.append(vuln)
                                    vuln_index += 1
                        
                        current = current.find_next_sibling()
        
        self.logger.info(f"Extracted {len(vulnerabilities)} vulnerabilities from Code4rena report")
        
        # Log breakdown by severity
        severity_counts = {}
        for vuln in vulnerabilities:
            severity_counts[vuln.severity] = severity_counts.get(vuln.severity, 0) + 1
        
        if severity_counts:
            breakdown = ", ".join([f"{sev.capitalize()}={count}" for sev, count in severity_counts.items()])
            self.logger.info(f"Vulnerability breakdown: {breakdown}")
        
        return vulnerabilities