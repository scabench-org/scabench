import unittest
import json
from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Vulnerability, Codebase, Project, Dataset


class TestModels(unittest.TestCase):
    
    def test_vulnerability_to_dict(self):
        vuln = Vulnerability(
            finding_id="test_finding_001",
            severity="high",
            title="Test Vulnerability",
            description="This is a test vulnerability"
        )
        
        result = vuln.to_dict()
        self.assertEqual(result['finding_id'], "test_finding_001")
        self.assertEqual(result['severity'], "high")
        self.assertEqual(result['title'], "Test Vulnerability")
        self.assertEqual(result['description'], "This is a test vulnerability")
    
    def test_codebase_to_dict(self):
        codebase = Codebase(
            codebase_id="test_abc123",
            repo_url="https://github.com/test/repo",
            commit="abc123def456",
            tree_url="https://github.com/test/repo/tree/abc123def456"
        )
        
        result = codebase.to_dict()
        self.assertEqual(result['codebase_id'], "test_abc123")
        self.assertEqual(result['repo_url'], "https://github.com/test/repo")
        self.assertEqual(result['commit'], "abc123def456")
        self.assertEqual(result['tree_url'], "https://github.com/test/repo/tree/abc123def456")
        self.assertNotIn('tarball_url', result)
        self.assertNotIn('notes', result)
        
        codebase_with_optional = Codebase(
            codebase_id="test_abc123",
            repo_url="https://github.com/test/repo",
            commit="abc123def456",
            tree_url="https://github.com/test/repo/tree/abc123def456",
            tarball_url="https://github.com/test/repo/archive/abc123def456.tar.gz",
            notes="Has submodules"
        )
        
        result = codebase_with_optional.to_dict()
        self.assertIn('tarball_url', result)
        self.assertIn('notes', result)
    
    def test_project_to_dict(self):
        codebase = Codebase(
            codebase_id="test_abc123",
            repo_url="https://github.com/test/repo",
            commit="abc123def456",
            tree_url="https://github.com/test/repo/tree/abc123def456"
        )
        
        vuln = Vulnerability(
            finding_id="test_finding_001",
            severity="high",
            title="Test Vulnerability",
            description="This is a test vulnerability"
        )
        
        project = Project(
            project_id="test_project_2024_03",
            name="Test Project",
            platform="test_platform",
            codebases=[codebase],
            vulnerabilities=[vuln]
        )
        
        result = project.to_dict()
        self.assertEqual(result['project_id'], "test_project_2024_03")
        self.assertEqual(result['name'], "Test Project")
        self.assertEqual(result['platform'], "test_platform")
        self.assertEqual(len(result['codebases']), 1)
        self.assertEqual(len(result['vulnerabilities']), 1)
        self.assertNotIn('contest_date', result)
        self.assertNotIn('report_url', result)
    
    def test_dataset_to_json(self):
        project = Project(
            project_id="test_project_2024_03",
            name="Test Project",
            platform="test_platform"
        )
        
        dataset = Dataset(
            dataset_id="test_dataset_2024",
            period_start="2024-01-01",
            period_end="2024-12-31",
            projects=[project]
        )
        
        json_str = dataset.to_json()
        parsed = json.loads(json_str)
        
        self.assertEqual(parsed['dataset_id'], "test_dataset_2024")
        self.assertEqual(parsed['period_start'], "2024-01-01")
        self.assertEqual(parsed['period_end'], "2024-12-31")
        self.assertEqual(parsed['schema_version'], "1.0.0")
        self.assertEqual(len(parsed['projects']), 1)


if __name__ == '__main__':
    unittest.main()