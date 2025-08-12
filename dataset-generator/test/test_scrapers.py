#!/usr/bin/env python3
"""
Comprehensive test suite for all scrapers
"""

import unittest
import sys
import os
import re
import json
from datetime import datetime
from bs4 import BeautifulSoup
import PyPDF2

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import scrapers to ensure they're registered
from scrapers.code4rena_scraper import Code4renaScraper
from scrapers.cantina_scraper import CantinaScraper
from scrapers.sherlock_scraper import SherlockScraper
from scraper import ScraperOrchestrator


class TestCode4renaScraper(unittest.TestCase):
    """Test Code4rena scraper functionality"""
    
    def setUp(self):
        self.scraper = Code4renaScraper(test_mode=True, test_data_dir='test/testdata')
        self.test_contest_id = '2025-04-virtuals-protocol'
        
    def test_vulnerability_extraction_accuracy(self):
        """Test that all vulnerabilities are extracted correctly"""
        # Manually count expected vulnerabilities
        with open('test/testdata/codearena-2025-04-virtuals-protocol.html', 'r') as f:
            html = f.read()
        
        text = BeautifulSoup(html, 'html.parser').get_text()
        
        # Count unique findings
        h_findings = set(re.findall(r'\[H-\d+\]', text))
        m_findings = set(re.findall(r'\[M-\d+\]', text))
        
        expected_high = len(h_findings)
        expected_medium = len(m_findings)
        expected_total = expected_high + expected_medium
        
        # Test scraper
        report = self.scraper.fetch_report(self.test_contest_id)
        
        self.assertIsNotNone(report, "Report should not be None")
        
        vulns = report.get('vulnerabilities', [])
        actual_high = sum(1 for v in vulns if v['severity'] == 'high')
        actual_medium = sum(1 for v in vulns if v['severity'] == 'medium')
        
        self.assertEqual(actual_high, expected_high, 
                        f"High severity: expected {expected_high}, got {actual_high}")
        self.assertEqual(actual_medium, expected_medium,
                        f"Medium severity: expected {expected_medium}, got {actual_medium}")
        self.assertEqual(len(vulns), expected_total,
                        f"Total vulnerabilities: expected {expected_total}, got {len(vulns)}")
    
    def test_github_url_extraction(self):
        """Test GitHub URL extraction"""
        report = self.scraper.fetch_report(self.test_contest_id)
        
        self.assertIsNotNone(report)
        self.assertTrue(len(report.get('codebases', [])) > 0, 
                       "Should extract at least one codebase")
        
        # Check for known GitHub URL patterns
        codebases = report.get('codebases', [])
        has_valid_url = any('github.com' in cb.get('repo_url', '') for cb in codebases)
        self.assertTrue(has_valid_url, "Should extract GitHub URLs")
    
    def test_project_metadata(self):
        """Test project metadata extraction"""
        report = self.scraper.fetch_report(self.test_contest_id)
        
        self.assertIsNotNone(report)
        self.assertIn('name', report)
        self.assertIn('platform', report)
        self.assertEqual(report['platform'], 'code4rena')
        self.assertIn('project_id', report)
        self.assertIn('report_url', report)


class TestCantinaScraper(unittest.TestCase):
    """Test Cantina scraper functionality"""
    
    def setUp(self):
        self.scraper = CantinaScraper(test_mode=True, test_data_dir='test/testdata')
        self.test_contest_id = '80b2fc65-3c2e-4ae7-8e48-6383fa936e6d'
    
    def test_vulnerability_extraction_accuracy(self):
        """Test that all vulnerabilities are extracted correctly"""
        # Expected counts from manual analysis
        expected_counts = {
            'critical': 1,
            'high': 1,
            'medium': 3,
            'informational': 2
        }
        expected_total = sum(expected_counts.values())
        
        # Test scraper
        report = self.scraper.fetch_report(self.test_contest_id)
        
        self.assertIsNotNone(report, "Report should not be None")
        
        vulns = report.get('vulnerabilities', [])
        actual_counts = {}
        for vuln in vulns:
            sev = vuln.get('severity', '')
            actual_counts[sev] = actual_counts.get(sev, 0) + 1
        
        for severity, expected in expected_counts.items():
            actual = actual_counts.get(severity, 0)
            self.assertEqual(actual, expected,
                           f"{severity.capitalize()}: expected {expected}, got {actual}")
        
        self.assertEqual(len(vulns), expected_total,
                        f"Total vulnerabilities: expected {expected_total}, got {len(vulns)}")
    
    def test_github_url_extraction(self):
        """Test GitHub URL extraction"""
        report = self.scraper.fetch_report(self.test_contest_id)
        
        self.assertIsNotNone(report)
        codebases = report.get('codebases', [])
        self.assertTrue(len(codebases) > 0, "Should extract at least one codebase")
        
        # Check for specific expected repo
        repo_urls = [cb.get('repo_url', '') for cb in codebases]
        self.assertTrue(any('PaintSwap/sonic-airdrop-contracts' in url for url in repo_urls),
                       "Should extract PaintSwap/sonic-airdrop-contracts repo")
    
    def test_vulnerability_titles(self):
        """Test that vulnerability titles are properly extracted"""
        report = self.scraper.fetch_report(self.test_contest_id)
        
        self.assertIsNotNone(report)
        vulns = report.get('vulnerabilities', [])
        
        # Check that all vulnerabilities have titles
        for vuln in vulns:
            self.assertIn('title', vuln)
            self.assertTrue(len(vuln['title']) > 5, 
                          f"Title should be meaningful: {vuln.get('title', '')}")
            self.assertIn('severity', vuln)
            self.assertIn('finding_id', vuln)


class TestSherlockScraper(unittest.TestCase):
    """Test Sherlock scraper functionality"""
    
    def setUp(self):
        self.scraper = SherlockScraper(test_mode=True, test_data_dir='test/testdata')
        self.test_contest_id = '2024.03.27 - Final - MetaLend Audit Report'
    
    def test_pdf_parsing(self):
        """Test PDF parsing and vulnerability extraction"""
        report = self.scraper.fetch_report(self.test_contest_id)
        
        self.assertIsNotNone(report, "Report should not be None")
        
        # Expected: 2 Low severity findings (L-1, L-2)
        vulns = report.get('vulnerabilities', [])
        self.assertEqual(len(vulns), 2, f"Expected 2 vulnerabilities, got {len(vulns)}")
        
        # Check severity
        for vuln in vulns:
            self.assertEqual(vuln['severity'], 'low', 
                           f"All findings should be low severity, got {vuln['severity']}")
    
    def test_project_name_extraction(self):
        """Test project name extraction from PDF"""
        report = self.scraper.fetch_report(self.test_contest_id)
        
        self.assertIsNotNone(report)
        self.assertIn('name', report)
        # The name should not be the malformed PDF data
        self.assertNotIn('burl@', report['name'], 
                        "Project name should not contain PDF rendering artifacts")
    
    def test_github_extraction(self):
        """Test GitHub URL extraction from PDF"""
        report = self.scraper.fetch_report(self.test_contest_id)
        
        self.assertIsNotNone(report)
        codebases = report.get('codebases', [])
        
        if codebases:
            # Check that URLs are valid
            for cb in codebases:
                url = cb.get('repo_url', '')
                if url:
                    self.assertIn('github', url.lower(), 
                                 f"Should be a GitHub URL: {url}")


class TestCLI(unittest.TestCase):
    """Test CLI functionality"""
    
    def test_list_platforms(self):
        """Test --list-platforms option"""
        import subprocess
        
        result = subprocess.run(
            ['python', 'scraper.py', '--list-platforms'],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, "Should exit successfully")
        self.assertIn('code4rena', result.stdout)
        self.assertIn('cantina', result.stdout)
        self.assertIn('sherlock', result.stdout)
    
    def test_help(self):
        """Test --help option"""
        import subprocess
        
        result = subprocess.run(
            ['python', 'scraper.py', '--help'],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, "Should exit successfully")
        self.assertIn('--platforms', result.stdout)
        self.assertIn('--months', result.stdout)
        self.assertIn('--test-mode', result.stdout)
    
    def test_single_platform_scraping(self):
        """Test scraping a single platform"""
        import subprocess
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            output_file = tmp.name
        
        try:
            result = subprocess.run(
                ['python', 'scraper.py',
                 '--platforms', 'code4rena',
                 '--months', '1',
                 '--test-mode',
                 '--test-data-dir', 'test/testdata',
                 '--output', output_file],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            self.assertEqual(result.returncode, 0, 
                           f"Should exit successfully: {result.stderr}")
            
            # Check output file was created and contains data
            self.assertTrue(os.path.exists(output_file), "Output file should be created")
            
            with open(output_file, 'r') as f:
                data = json.load(f)
            
            self.assertIn('projects', data)
            self.assertIn('dataset_id', data)
            self.assertIn('period_start', data)
            self.assertIn('period_end', data)
            
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete system"""
    
    def setUp(self):
        """Ensure scrapers are imported and registered"""
        # Force import of scrapers to ensure registration
        import scrapers.code4rena_scraper
        import scrapers.cantina_scraper
        import scrapers.sherlock_scraper
    
    def test_end_to_end_scraping(self):
        """Test complete end-to-end scraping workflow"""
        # Direct test with a single scraper
        scraper = CantinaScraper(test_mode=True, test_data_dir='test/testdata')
        
        # Test fetching contests
        contests = scraper.fetch_contests(
            period_start=datetime(2025, 7, 1),
            period_end=datetime(2025, 8, 1)
        )
        self.assertTrue(len(contests) > 0, "Should find contests")
        
        # Test fetching a report
        if contests:
            report = scraper.fetch_report(contests[0]['id'])
            self.assertIsNotNone(report, "Should fetch report")
            self.assertIn('vulnerabilities', report)
            self.assertTrue(len(report['vulnerabilities']) > 0, "Should extract vulnerabilities")


def suite():
    """Create test suite"""
    test_suite = unittest.TestSuite()
    
    # Add all test cases
    test_suite.addTest(unittest.makeSuite(TestCode4renaScraper))
    test_suite.addTest(unittest.makeSuite(TestCantinaScraper))
    test_suite.addTest(unittest.makeSuite(TestSherlockScraper))
    test_suite.addTest(unittest.makeSuite(TestCLI))
    test_suite.addTest(unittest.makeSuite(TestIntegration))
    
    return test_suite


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite())