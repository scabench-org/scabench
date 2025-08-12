import unittest
from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base_scraper import BaseScraper


class ConcreteBaseScraper(BaseScraper):
    """Concrete implementation for testing - not a test class"""
    def fetch_contests(self, period_start, period_end):
        return []
    
    def fetch_report(self, contest_id):
        return None


class TestBaseScraperMethods(unittest.TestCase):
    
    def setUp(self):
        self.scraper = ConcreteBaseScraper("test_platform")
    
    def test_normalize_project_id(self):
        date = datetime(2024, 3, 15)
        result = self.scraper.normalize_project_id("Test Project", date)
        self.assertEqual(result, "test_platform_test-project_2024_03")
        
        result = self.scraper.normalize_project_id("Test_Project!", date)
        self.assertEqual(result, "test_platform_test-project_2024_03")
    
    def test_normalize_codebase_id(self):
        commit = "5b6f1c5a9de5a6d2b6b1a2e3f4c5d6e7f8a9b0c1"
        result = self.scraper.normalize_codebase_id("project", commit)
        self.assertEqual(result, "project_5b6f1c")
        
        short_commit = "abc123"
        result = self.scraper.normalize_codebase_id("test", short_commit)
        self.assertEqual(result, "test_abc123")
    
    def test_normalize_finding_id(self):
        result = self.scraper.normalize_finding_id("project-slug", "H-01")
        self.assertEqual(result, "test_platform_project-slug_H-01")
        
        result = self.scraper.normalize_finding_id("project-slug", index=5)
        self.assertEqual(result, "test_platform_project-slug_005")
    
    def test_create_tree_url(self):
        repo_url = "https://github.com/org/repo"
        commit = "abc123def456"
        result = self.scraper.create_tree_url(repo_url, commit)
        self.assertEqual(result, "https://github.com/org/repo/tree/abc123def456")
        
        repo_url_with_git = "https://github.com/org/repo.git"
        result = self.scraper.create_tree_url(repo_url_with_git, commit)
        self.assertEqual(result, "https://github.com/org/repo/tree/abc123def456")
    
    def test_create_tarball_url(self):
        repo_url = "https://github.com/org/repo"
        commit = "abc123def456"
        result = self.scraper.create_tarball_url(repo_url, commit)
        self.assertEqual(result, "https://github.com/org/repo/archive/abc123def456.tar.gz")
    
    def test_normalize_severity(self):
        self.assertEqual(self.scraper.normalize_severity("High"), "high")
        self.assertEqual(self.scraper.normalize_severity("CRITICAL"), "high")
        self.assertEqual(self.scraper.normalize_severity("Medium"), "medium")
        self.assertEqual(self.scraper.normalize_severity("Med"), "medium")
        self.assertEqual(self.scraper.normalize_severity("Low"), "low")
        self.assertEqual(self.scraper.normalize_severity("Info"), "unknown")


if __name__ == '__main__':
    unittest.main()