from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
import requests
from bs4 import BeautifulSoup
import re
import os
import json

from base_scraper import BaseScraper
from scraper_factory import register_scraper
from models import Project, Codebase, Vulnerability

logger = logging.getLogger(__name__)


@register_scraper("cantina")
class CantinaScraper(BaseScraper):
    
    BASE_URL = "https://cantina.xyz"
    PORTFOLIO_URL = f"{BASE_URL}/portfolio"
    
    def __init__(self, platform: str = "cantina", test_mode: bool = False, test_data_dir: str = None):
        super().__init__(platform, test_mode, test_data_dir)
    
    def fetch_contests(self, period_start: datetime, period_end: datetime) -> List[Dict[str, Any]]:
        self.logger.info(f"Fetching Cantina contests from {period_start} to {period_end}")
        contests = []
        
        try:
            if self.test_mode and self.test_data_dir:
                # Load from local test data
                test_file = os.path.join(self.test_data_dir, 'cantina-portfolio.html')
                with open(test_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            else:
                response = requests.get(self.PORTFOLIO_URL, timeout=30)
                response.raise_for_status()
                html_content = response.text
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract portfolio links - they are UUIDs
            # Pattern: /portfolio/[uuid]
            # The <a> tags with class "chakra-card" ARE the cards themselves
            cards = soup.find_all('a', class_=re.compile('chakra-card'))
            
            for card in cards:
                href = card.get('href', '')
                if '/portfolio/' in href:
                    contest_id = href.split('/')[-1]
                    
                    project_name = contest_id  # Default
                    contest_date = None
                    
                    # Look for project name in the card
                    name_elem = card.find('p', class_=re.compile('css-a6v8hi'))
                    if name_elem:
                        project_name = name_elem.get_text(strip=True)
                    
                    # Look for date range in the card - format: "DD Month YYYY - DD Month YYYY"
                    date_elems = card.find_all('span', class_=re.compile('css-ulwnsq'))
                    for date_elem in date_elems:
                        date_text = date_elem.get_text(strip=True)
                        # Extract start date from range like "25 July 2025 - 30 July 2025"
                        date_match = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})', date_text)
                        if date_match:
                            day, month_name, year = date_match.groups()
                            try:
                                month_map = {
                                    'January': 1, 'February': 2, 'March': 3, 'April': 4,
                                    'May': 5, 'June': 6, 'July': 7, 'August': 8,
                                    'September': 9, 'October': 10, 'November': 11, 'December': 12
                                }
                                month = month_map.get(month_name, 1)
                                contest_date = datetime(int(year), month, int(day))
                                break
                            except:
                                pass
                    
                    # If we couldn't extract date from card, use current date as fallback
                    if not contest_date:
                        contest_date = datetime.now()
                        self.logger.warning(f"Could not extract date for contest {contest_id}, using current date")
                    
                    if period_start <= contest_date <= period_end:
                        contests.append({
                            'id': contest_id,
                            'name': project_name,
                            'date': contest_date,
                            'url': f"{self.BASE_URL}/portfolio/{contest_id}"
                        })
            
            self.logger.info(f"Found {len(contests)} Cantina contests in date range")
            
        except Exception as e:
            self.logger.error(f"Error parsing Cantina contests: {e}")
        
        return contests
    
    def fetch_report(self, contest_id: str) -> Optional[Dict[str, Any]]:
        self.logger.info(f"Fetching Cantina report for contest: {contest_id}")
        
        try:
            if self.test_mode and self.test_data_dir:
                # Try to load from local test data
                # Map the UUID to our test file
                if '80b2fc65' in contest_id:  # Sonic report UUID
                    test_file = os.path.join(self.test_data_dir, 'cantina-sonic.html')
                else:
                    # Default to sonic report for testing
                    test_file = os.path.join(self.test_data_dir, 'cantina-sonic.html')
                
                with open(test_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                report_url = f"{self.BASE_URL}/portfolio/{contest_id}"
            else:
                report_url = f"{self.BASE_URL}/portfolio/{contest_id}"
                response = requests.get(report_url, timeout=30)
                response.raise_for_status()
                html_content = response.text
            
            soup = BeautifulSoup(html_content, 'html.parser')
            project = self._parse_report(soup, contest_id, report_url)
            
            if project:
                return project.to_dict()
            
        except Exception as e:
            self.logger.error(f"Error parsing report for {contest_id}: {e}")
        
        return None
    
    def _parse_report(self, soup: BeautifulSoup, contest_id: str, report_url: str) -> Optional[Project]:
        try:
            # Extract project name from h1 tag
            project_name = self._extract_project_name(soup) or "Unknown Project"
            
            # Extract date from meta description or content
            contest_date = self._extract_date(soup) or datetime.now()
            
            project_id = self.normalize_project_id(project_name, contest_date)
            
            project = Project(
                project_id=project_id,
                name=project_name,
                platform=self.platform,
                contest_date=contest_date,
                report_url=report_url
            )
            
            # Extract GitHub repository information
            github_info = self._extract_github_info(soup)
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
            
            # Extract vulnerabilities from the report
            vulnerabilities = self._extract_vulnerabilities(soup, contest_id)
            project.vulnerabilities.extend(vulnerabilities)
            
            self.logger.info(f"Parsed Cantina report: {project_name} with {len(vulnerabilities)} findings")
            
            return project
            
        except Exception as e:
            self.logger.error(f"Error parsing report for {contest_id}: {e}")
            return None
    
    def _extract_project_name(self, soup: BeautifulSoup) -> Optional[str]:
        # Try h1 first
        h1_tag = soup.find('h1')
        if h1_tag:
            text = h1_tag.get_text(strip=True)
            # Clean up if needed
            if '|' in text:
                text = text.split('|')[0].strip()
            return text
        
        # Fallback to title tag
        title_tag = soup.find('title')
        if title_tag:
            text = title_tag.get_text(strip=True)
            if '|' in text:
                text = text.split('|')[0].strip()
            return text
        
        return None
    
    def _extract_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        # Try to find date in meta description first
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc:
            content = meta_desc.get('content', '')
            # Look for date patterns like "From 25 July 2025 to 30 July 2025"
            date_pattern = r'From (\d{1,2}) (\w+) (\d{4})'
            match = re.search(date_pattern, content)
            if match:
                day, month_name, year = match.groups()
                try:
                    # Convert month name to number
                    month_map = {
                        'January': 1, 'February': 2, 'March': 3, 'April': 4,
                        'May': 5, 'June': 6, 'July': 7, 'August': 8,
                        'September': 9, 'October': 10, 'November': 11, 'December': 12
                    }
                    month = month_map.get(month_name, 1)
                    return datetime(int(year), month, int(day))
                except:
                    pass
        
        # Fallback to searching in text
        date_pattern = r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})'
        text = soup.get_text()
        match = re.search(date_pattern, text)
        
        if match:
            year, month, day = match.groups()
            try:
                return datetime(int(year), int(month), int(day))
            except ValueError:
                pass
        
        return None
    
    def _extract_github_info(self, soup: BeautifulSoup) -> Optional[tuple]:
        # Look for GitHub URLs in meta description
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc:
            content = meta_desc.get('content', '')
            # Pattern like "https://github.com/PaintSwap/sonic-airdrop-contracts on commit hash 09a09846..."
            github_pattern = r'(https://github\.com/[^\s]+)\s+on\s+commit\s+hash\s+([a-f0-9]+)'
            match = re.search(github_pattern, content)
            if match:
                repo_url = match.group(1).rstrip('/').rstrip('.git')
                commit = match.group(2)
                return repo_url, commit
        
        # Fallback to searching for GitHub links in the page
        github_links = soup.find_all('a', href=re.compile(r'github\.com'))
        
        for link in github_links:
            href = link.get('href', '')
            if '/tree/' in href or '/commit/' in href:
                parts = href.split('/')
                if len(parts) >= 7:
                    org = parts[3]
                    repo = parts[4]
                    commit = parts[6] if len(parts) > 6 else None
                    repo_url = f"https://github.com/{org}/{repo}"
                    return repo_url, commit
        
        # Search in text for GitHub URLs
        text = soup.get_text()
        github_pattern = r'https://github\.com/([^/]+)/([^/\s]+)'
        match = re.search(github_pattern, text)
        if match:
            org = match.group(1)
            repo = match.group(2).rstrip('.').rstrip(',').rstrip(')')
            repo_url = f"https://github.com/{org}/{repo}"
            
            # Try to find commit hash nearby
            commit_pattern = r'\b([a-f0-9]{40})\b|\b([a-f0-9]{7,10})\b'
            commit_match = re.search(commit_pattern, text)
            commit = commit_match.group(1) or commit_match.group(2) if commit_match else None
            
            return repo_url, commit
        
        return None
    
    def _extract_vulnerabilities(self, soup: BeautifulSoup, contest_id: str) -> List[Vulnerability]:
        """Extract vulnerabilities from Cantina report HTML"""
        vulnerabilities = []
        
        try:
            # Find the main findings section
            # Structure: h2 "Findings" -> h3 "Critical Risk" -> h4 (finding titles)
            
            # Track finding counts per severity
            finding_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
            
            # Find all severity sections
            severity_sections = [
                ('Critical Risk', 'critical'),
                ('High Risk', 'high'),
                ('Medium Risk', 'medium'),
                ('Low Risk', 'low'),
                ('Informational', 'informational')
            ]
            
            for severity_label, severity in severity_sections:
                # Find h3 tags that contain the severity label
                severity_headers = soup.find_all('h3', string=re.compile(severity_label, re.IGNORECASE))
                
                for severity_header in severity_headers:
                    # Extract the count from the header (e.g., "Critical Risk 1 finding")
                    header_text = severity_header.get_text(strip=True)
                    count_match = re.search(r'(\d+)\s*finding', header_text)
                    expected_count = int(count_match.group(1)) if count_match else 0
                    
                    # Find all h4 tags after this h3 (these are the finding titles)
                    current = severity_header.find_next_sibling()
                    
                    while current:
                        if current.name == 'h3':  # Stop at next severity section
                            break
                        elif current.name == 'h4':
                            title = current.get_text(strip=True)
                            
                            # Clean up the title
                            title = re.sub(r'^\d+\.\s*', '', title)  # Remove numbering
                            
                            if title and len(title) > 3:  # Filter out empty or very short titles
                                finding_counts[severity] += 1
                                finding_id = f"{contest_id}_{severity[0].upper()}-{finding_counts[severity]:02d}"
                                
                                # Try to extract description from the next few elements
                                description = self._extract_finding_description(current)
                                
                                vuln = Vulnerability(
                                    finding_id=finding_id,
                                    severity=severity,
                                    title=title,
                                    description=description
                                )
                                vulnerabilities.append(vuln)
                                
                                self.logger.debug(f"Found {severity} vulnerability: {title}")
                        
                        current = current.find_next_sibling()
                    
                    # Log if count mismatch
                    if expected_count > 0 and finding_counts[severity] != expected_count:
                        self.logger.warning(
                            f"Count mismatch for {severity}: expected {expected_count}, found {finding_counts[severity]}"
                        )
            
            # Also look for any h4 elements that might be findings we missed
            all_h4 = soup.find_all('h4')
            for h4 in all_h4:
                title = h4.get_text(strip=True)
                # Check if this looks like a finding title and we haven't already captured it
                if title and len(title) > 10 and not any(v.title == title for v in vulnerabilities):
                    # Check what severity section this belongs to
                    severity = self._determine_severity_from_context(h4)
                    if severity:
                        finding_counts[severity] = finding_counts.get(severity, 0) + 1
                        finding_id = f"{contest_id}_{severity[0].upper()}-{finding_counts[severity]:02d}"
                        
                        description = self._extract_finding_description(h4)
                        
                        vuln = Vulnerability(
                            finding_id=finding_id,
                            severity=severity,
                            title=title,
                            description=description
                        )
                        vulnerabilities.append(vuln)
            
            self.logger.info(
                f"Extracted {len(vulnerabilities)} vulnerabilities: "
                f"Critical={finding_counts.get('critical', 0)}, "
                f"High={finding_counts.get('high', 0)}, "
                f"Medium={finding_counts.get('medium', 0)}, "
                f"Low={finding_counts.get('low', 0)}"
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting vulnerabilities: {e}")
        
        return vulnerabilities
    
    def _extract_finding_description(self, heading_element) -> str:
        """Extract description text after a finding heading"""
        description_parts = []
        current = heading_element.find_next_sibling()
        max_elements = 3  # Look at next few elements
        
        while current and max_elements > 0:
            if current.name in ['h2', 'h3', 'h4']:  # Stop at next heading
                break
            
            text = current.get_text(strip=True)
            if text and len(text) > 20:  # Meaningful text
                description_parts.append(text[:500])  # Limit length
                break  # Usually first paragraph is enough
            
            current = current.find_next_sibling()
            max_elements -= 1
        
        return ' '.join(description_parts)[:1000]  # Limit total description length
    
    def _determine_severity_from_context(self, element) -> Optional[str]:
        """Determine severity by looking at parent/previous elements"""
        # Look for previous h3 that indicates severity
        prev = element.find_previous('h3')
        if prev:
            text = prev.get_text(strip=True).lower()
            if 'critical' in text:
                return 'critical'
            elif 'high' in text:
                return 'high'
            elif 'medium' in text:
                return 'medium'
            elif 'low' in text:
                return 'low'
            elif 'informational' in text:
                return 'informational'
        return None