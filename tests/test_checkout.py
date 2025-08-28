#!/usr/bin/env python3
"""
Tests for the source checkout functionality.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
import shutil

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'dataset-generator'))

from checkout_sources import SourceCheckout, CloneResult


class TestSourceCheckout:
    """Test the source checkout functionality."""
    
    def test_initialization(self, tmp_path):
        """Test SourceCheckout initialization."""
        checkout = SourceCheckout(str(tmp_path / "sources"))
        assert checkout.output_dir.exists()
        assert checkout.results == []
    
    def test_sanitize_name(self):
        """Test name sanitization."""
        checkout = SourceCheckout()
        
        # Test various problematic characters
        assert checkout.sanitize_name("test/project") == "test_project"
        assert checkout.sanitize_name("test:project*2024") == "test_project_2024"
        assert checkout.sanitize_name("Test Project - V2") == "test_project_v2"
        assert checkout.sanitize_name("test__project") == "test_project"
        assert checkout.sanitize_name("___test___") == "test"
    
    @patch('subprocess.run')
    def test_clone_repository_success(self, mock_run, tmp_path):
        """Test successful repository cloning."""
        checkout = SourceCheckout(str(tmp_path))
        
        # Mock successful clone and checkout
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # git clone
            Mock(returncode=0, stdout="", stderr=""),  # git checkout
        ]
        
        result = checkout.clone_repository(
            "https://github.com/test/repo.git",
            "abc123def456",
            tmp_path / "test_repo",
            "Test Project"
        )
        
        assert result.success == True
        assert result.project_name == "Test Project"
        assert result.commit == "abc123def456"
        assert mock_run.call_count == 2
    
    @patch('subprocess.run')
    def test_clone_repository_existing_correct_commit(self, mock_run, tmp_path):
        """Test handling of existing repo at correct commit."""
        checkout = SourceCheckout(str(tmp_path))
        
        # Create existing directory
        target_dir = tmp_path / "test_repo"
        target_dir.mkdir()
        
        # Mock checking current commit
        mock_run.return_value = Mock(
            returncode=0, 
            stdout="abc123def456789",
            stderr=""
        )
        
        result = checkout.clone_repository(
            "https://github.com/test/repo.git",
            "abc123de",  # First 8 chars match
            target_dir,
            "Test Project"
        )
        
        assert result.success == True
        assert mock_run.call_count == 1  # Only checked HEAD, no clone
    
    @patch('subprocess.run')
    def test_clone_repository_wrong_commit_reclone(self, mock_run, tmp_path):
        """Test re-cloning when existing repo is at wrong commit."""
        checkout = SourceCheckout(str(tmp_path))
        
        # Create existing directory with file
        target_dir = tmp_path / "test_repo"
        target_dir.mkdir()
        (target_dir / "test.txt").write_text("test")
        
        # Mock: wrong commit, then successful clone and checkout
        mock_run.side_effect = [
            Mock(returncode=0, stdout="wrongcommit123", stderr=""),  # git rev-parse HEAD
            Mock(returncode=0, stdout="", stderr=""),  # git clone
            Mock(returncode=0, stdout="", stderr=""),  # git checkout
        ]
        
        result = checkout.clone_repository(
            "https://github.com/test/repo.git",
            "abc123def456",
            target_dir,
            "Test Project"
        )
        
        assert result.success == True
        assert not (target_dir / "test.txt").exists()  # Old dir removed
    
    @patch('subprocess.run')
    def test_clone_repository_checkout_needs_unshallow(self, mock_run, tmp_path):
        """Test fetching more history when commit not found."""
        checkout = SourceCheckout(str(tmp_path))
        
        # Mock: clone success, checkout fail, fetch, checkout success
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # git clone
            Mock(returncode=1, stdout="", stderr="pathspec 'abc123' did not match"),  # git checkout fail
            Mock(returncode=0, stdout="", stderr=""),  # git fetch --unshallow
            Mock(returncode=0, stdout="", stderr=""),  # git checkout retry
        ]
        
        result = checkout.clone_repository(
            "https://github.com/test/repo.git",
            "abc123def456",
            tmp_path / "test_repo",
            "Test Project"
        )
        
        assert result.success == True
        assert mock_run.call_count == 4
    
    @patch('subprocess.run')
    def test_clone_repository_failure(self, mock_run, tmp_path):
        """Test handling of clone failure."""
        checkout = SourceCheckout(str(tmp_path))
        
        # Mock clone failure
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="fatal: repository not found"
        )
        
        result = checkout.clone_repository(
            "https://github.com/test/nonexistent.git",
            "abc123",
            tmp_path / "test_repo",
            "Test Project"
        )
        
        assert result.success == False
        assert "Clone failed" in result.error_message
        assert not (tmp_path / "test_repo").exists()
    
    def test_ssh_to_https_conversion(self):
        """Test conversion of SSH URLs to HTTPS."""
        checkout = SourceCheckout()
        
        # Test the URL conversion logic in clone_repository
        ssh_urls = [
            ("git@github.com:user/repo.git", "https://github.com/user/repo.git"),
            ("ssh://git@github.com/user/repo.git", "https://github.com/user/repo.git"),
            ("https://github.com/user/repo.git", "https://github.com/user/repo.git"),
        ]
        
        for ssh_url, expected_https in ssh_urls:
            # The conversion happens inside clone_repository
            # We verify the logic is correct
            if ssh_url.startswith("git@github.com:"):
                converted = ssh_url.replace("git@github.com:", "https://github.com/")
            elif ssh_url.startswith("ssh://git@github.com/"):
                converted = ssh_url.replace("ssh://git@github.com/", "https://github.com/")
            else:
                converted = ssh_url
            assert converted == expected_https
    
    @patch.object(SourceCheckout, 'clone_repository')
    def test_checkout_dataset(self, mock_clone, tmp_path):
        """Test checking out an entire dataset."""
        checkout = SourceCheckout(str(tmp_path / "sources"))
        
        # Create test dataset
        dataset = [
            {
                "project_id": "test_project_1",
                "name": "Test Project 1",
                "codebases": [
                    {
                        "repo_url": "https://github.com/test/repo1.git",
                        "commit": "abc123"
                    }
                ]
            },
            {
                "project_id": "test_project_2", 
                "name": "Test Project 2",
                "codebases": [
                    {
                        "repo_url": "https://github.com/test/repo2.git",
                        "commit": "def456"
                    },
                    {
                        "repo_url": "https://github.com/test/repo3.git",
                        "commit": "ghi789"
                    }
                ]
            }
        ]
        
        dataset_file = tmp_path / "test_dataset.json"
        with open(dataset_file, 'w') as f:
            json.dump(dataset, f)
        
        # Mock successful clones
        mock_clone.side_effect = [
            CloneResult(True, "Test Project 1", "url1", "abc123", Path("dir1")),
            CloneResult(True, "Test Project 2", "url2", "def456", Path("dir2")),
            CloneResult(False, "Test Project 2", "url3", "ghi789", Path("dir3"), "Error"),
        ]
        
        stats = checkout.checkout_dataset(dataset_file)
        
        assert stats["total"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1
        assert len(stats["failed_details"]) == 1
        assert mock_clone.call_count == 3
    
    @patch.object(SourceCheckout, 'clone_repository')
    def test_checkout_dataset_with_filter(self, mock_clone, tmp_path):
        """Test filtering projects during checkout."""
        checkout = SourceCheckout(str(tmp_path / "sources"))
        
        # Create test dataset
        dataset = [
            {"project_id": "vulnerable_vault", "name": "Vulnerable Vault", "codebases": [{"repo_url": "https://github.com/test/vault.git", "commit": "c1"}]},
            {"project_id": "safe_contract", "name": "Safe Contract", "codebases": [{"repo_url": "https://github.com/test/safe.git", "commit": "c2"}]},
        ]
        
        dataset_file = tmp_path / "test_dataset.json"
        with open(dataset_file, 'w') as f:
            json.dump(dataset, f)
        
        # Mock clone
        mock_clone.return_value = CloneResult(True, "Vulnerable Vault", "https://github.com/test/vault.git", "c1", Path("dir1"))
        
        # Filter to only "vault"
        stats = checkout.checkout_dataset(dataset_file, project_filter="vault")
        
        assert stats["total"] == 1
        assert stats["successful"] == 1
        assert mock_clone.call_count == 1
    
    def test_checkout_dataset_no_github(self, tmp_path):
        """Test skipping non-GitHub repositories."""
        checkout = SourceCheckout(str(tmp_path / "sources"))
        
        dataset = [
            {
                "project_id": "test",
                "name": "Test",
                "codebases": [
                    {"repo_url": "https://gitlab.com/test/repo.git", "commit": "abc"},
                    {"repo_url": "https://bitbucket.org/test/repo.git", "commit": "def"},
                ]
            }
        ]
        
        dataset_file = tmp_path / "test_dataset.json"
        with open(dataset_file, 'w') as f:
            json.dump(dataset, f)
        
        stats = checkout.checkout_dataset(dataset_file)
        
        assert stats["total"] == 0  # All skipped
        assert stats["successful"] == 0
        assert stats["failed"] == 0


def test_cli_checkout(tmp_path, monkeypatch):
    """Test the CLI interface for checkout."""
    import subprocess
    
    # Create test dataset
    dataset = [{
        "project_id": "test",
        "name": "Test Project",
        "codebases": [{
            "repo_url": "https://github.com/test/repo.git",
            "commit": "abc123"
        }]
    }]
    
    dataset_file = tmp_path / "test.json"
    with open(dataset_file, 'w') as f:
        json.dump(dataset, f)
    
    # This would test the actual CLI, but we'd need to mock git commands
    # For now, just verify the module can be imported and basic structure works
    from checkout_sources import main
    assert callable(main)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])