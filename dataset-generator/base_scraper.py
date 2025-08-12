from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    
    def __init__(self, platform: str, test_mode: bool = False, test_data_dir: str = None):
        self.platform = platform
        self.logger = logging.getLogger(f"{__name__}.{platform}")
        self.test_mode = test_mode
        self.test_data_dir = test_data_dir
    
    @abstractmethod
    def fetch_contests(self, period_start: datetime, period_end: datetime) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def fetch_report(self, contest_id: str) -> Optional[Dict[str, Any]]:
        pass
    
    def normalize_project_id(self, name: str, date: datetime) -> str:
        normalized_name = name.lower().replace(' ', '-').replace('_', '-')
        normalized_name = ''.join(c for c in normalized_name if c.isalnum() or c == '-')
        date_str = date.strftime('%Y_%m')
        return f"{self.platform}_{normalized_name}_{date_str}"
    
    def normalize_codebase_id(self, short_name: str, commit: str) -> str:
        commit_prefix = commit[:6] if len(commit) >= 6 else commit
        return f"{short_name}_{commit_prefix}"
    
    def normalize_finding_id(self, project_slug: str, original_label: str = None, index: int = None) -> str:
        if original_label:
            return f"{self.platform}_{project_slug}_{original_label}"
        else:
            return f"{self.platform}_{project_slug}_{index:03d}"
    
    def create_tree_url(self, repo_url: str, commit: str) -> str:
        if 'github.com' in repo_url:
            base_url = repo_url.replace('.git', '').rstrip('/')
            return f"{base_url}/tree/{commit}"
        return ""
    
    def create_tarball_url(self, repo_url: str, commit: str) -> str:
        if 'github.com' in repo_url:
            base_url = repo_url.replace('.git', '').replace('https://github.com/', '')
            return f"https://github.com/{base_url}/archive/{commit}.tar.gz"
        return ""
    
    def normalize_severity(self, severity: str) -> str:
        severity_lower = severity.lower()
        if 'high' in severity_lower or 'critical' in severity_lower:
            return 'high'
        elif 'medium' in severity_lower or 'med' in severity_lower:
            return 'medium'
        elif 'low' in severity_lower:
            return 'low'
        else:
            return 'unknown'