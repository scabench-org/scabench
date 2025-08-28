#!/usr/bin/env python3
"""
Integration tests for ScaBench tooling pipeline.
Tests the complete flow from baseline analysis to report generation.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'baseline-runner'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scoring'))

from baseline_runner import BaselineRunner, Finding, AnalysisResult
from scorer import ScaBenchScorer, MatchResult, ScoringResult
from report_generator import ReportGenerator


# Sample test data
SAMPLE_CONTRACT = """
pragma solidity ^0.8.0;

contract VulnerableVault {
    mapping(address => uint256) public balances;
    
    // Reentrancy vulnerability
    function withdraw(uint256 amount) external {
        require(balances[msg.sender] >= amount, "Insufficient balance");
        
        // Bug: State update after external call
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Transfer failed");
        
        balances[msg.sender] -= amount;
    }
    
    // Integer overflow (pre-0.8.0 style, but showing pattern)
    function deposit() external payable {
        // Could overflow in older versions
        balances[msg.sender] += msg.value;
    }
}
"""

SAMPLE_BENCHMARK_DATA = [
    {
        "project_id": "test_project_001",
        "name": "Test Vulnerable Vault",
        "vulnerabilities": [
            {
                "title": "Reentrancy vulnerability in withdraw function",
                "description": "The withdraw function updates state after making an external call, allowing reentrancy attacks",
                "vulnerability_type": "reentrancy",
                "severity": "high",
                "location": "withdraw() function"
            },
            {
                "title": "Missing zero address validation",
                "description": "Functions do not validate against zero address",
                "vulnerability_type": "input validation",
                "severity": "low",
                "location": "multiple functions"
            }
        ]
    }
]

SAMPLE_BASELINE_FINDINGS = [
    {
        "title": "Reentrancy vulnerability in withdraw function",
        "description": "The withdraw function makes an external call before updating the balance, enabling reentrancy attacks",
        "vulnerability_type": "reentrancy",
        "severity": "high",
        "confidence": 0.95,
        "location": "withdraw() function",
        "file": "VulnerableVault.sol"
    },
    {
        "title": "Potential integer overflow in deposit",
        "description": "Addition operation could overflow in older Solidity versions",
        "vulnerability_type": "integer overflow",
        "severity": "medium",
        "confidence": 0.7,
        "location": "deposit() function",
        "file": "VulnerableVault.sol"
    }
]


class TestBaselineRunner:
    """Test the baseline runner component."""
    
    def test_initialization(self):
        """Test BaselineRunner initialization."""
        config = {'model': 'gpt-4o', 'api_key': 'test_key'}
        runner = BaselineRunner(config)
        assert runner.model == 'gpt-4o'
        assert runner.api_key == 'test_key'
    
    def test_finding_creation(self):
        """Test Finding dataclass creation."""
        finding = Finding(
            title="Test vulnerability",
            description="Test description",
            vulnerability_type="reentrancy",
            severity="high",
            confidence=0.9,
            location="test()",
            file="test.sol"
        )
        assert finding.title == "Test vulnerability"
        assert finding.severity == "high"
        assert finding.id != ""  # Auto-generated
    
    @patch('baseline_runner.OpenAI')
    def test_analyze_file_mock(self, mock_openai):
        """Test file analysis with mocked LLM."""
        # Setup mock
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content=json.dumps([
            {
                "title": "Test vulnerability",
                "description": "Test description",
                "vulnerability_type": "reentrancy",
                "severity": "high",
                "confidence": 0.9,
                "location": "test()"
            }
        ])))]
        mock_response.usage = Mock(prompt_tokens=100, completion_tokens=50)
        
        mock_client.chat.completions.create.return_value = mock_response
        
        # Run test
        runner = BaselineRunner({'api_key': 'test'})
        findings, input_tokens, output_tokens = runner.analyze_file(
            Path("test.sol"),
            SAMPLE_CONTRACT
        )
        
        assert len(findings) == 1
        assert findings[0].title == "Test vulnerability"
        assert input_tokens == 100
        assert output_tokens == 50
    
    def test_select_files_for_analysis(self, tmp_path):
        """Test intelligent file selection."""
        runner = BaselineRunner({'api_key': 'test'})
        
        # Create temporary files for testing
        files = []
        file_names = [
            "Vault.sol",
            "Token.sol",
            "Oracle.sol",
            "test/TestVault.sol",
            "mock/MockToken.sol",
            "interfaces/IVault.sol",
            "libraries/Math.sol",
            "Governance.sol",
            "Staking.sol",
            "Router.sol",
        ]
        
        for name in file_names:
            file_path = tmp_path / name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("contract Test {}")
            files.append(file_path)
        
        selected = runner.select_files_for_analysis(files, 5)
        
        # Should prioritize core contracts over test/mock
        assert len(selected) == 5
        # Check that test/mock files are deprioritized
        selected_names = [f.name for f in selected]
        assert "TestVault.sol" not in selected_names
        assert "MockToken.sol" not in selected_names
        # Should include important contracts
        assert any("Vault.sol" in f.name for f in selected)


class TestScorer:
    """Test the scoring component."""
    
    def test_initialization(self):
        """Test ScaBenchScorer initialization."""
        config = {'model': 'gpt-4o', 'api_key': 'test_key'}
        scorer = ScaBenchScorer(config)
        assert scorer.model == 'gpt-4o'
        assert scorer.api_key == 'test_key'
    
    @patch('scorer.OpenAI')
    def test_match_finding_perfect_match(self, mock_openai):
        """Test perfect matching scenario."""
        # Setup mock for perfect match
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content=json.dumps({
            "matched": True,
            "confidence": 1.0,
            "justification": "Perfect match: same vulnerability in same location",
            "dismissal_reasons": []
        })))]
        
        mock_client.chat.completions.create.return_value = mock_response
        
        # Run test
        scorer = ScaBenchScorer({'api_key': 'test'})
        
        expected = SAMPLE_BENCHMARK_DATA[0]['vulnerabilities'][0]
        found = SAMPLE_BASELINE_FINDINGS[0]
        
        result = scorer.match_finding_with_llm(expected, found)
        
        assert result.matched == True
        assert result.confidence == 1.0
        assert "Perfect match" in result.justification
    
    @patch('scorer.OpenAI')
    def test_match_finding_no_match(self, mock_openai):
        """Test non-matching scenario."""
        # Setup mock for no match
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content=json.dumps({
            "matched": False,
            "confidence": 0.2,
            "justification": "Different vulnerability type and location",
            "dismissal_reasons": ["different_root_cause", "different_location"]
        })))]
        
        mock_client.chat.completions.create.return_value = mock_response
        
        # Run test
        scorer = ScaBenchScorer({'api_key': 'test'})
        
        expected = SAMPLE_BENCHMARK_DATA[0]['vulnerabilities'][1]
        found = SAMPLE_BASELINE_FINDINGS[1]
        
        result = scorer.match_finding_with_llm(expected, found)
        
        assert result.matched == False
        assert result.confidence < 1.0
        assert len(result.dismissal_reasons) > 0
    
    @patch.object(ScaBenchScorer, 'match_finding_with_llm')
    def test_score_project(self, mock_match):
        """Test complete project scoring."""
        # Setup mock matches - need 4 calls (2 expected x 2 found)
        mock_match.side_effect = [
            # First expected vs first found
            MatchResult(
                matched=True,
                confidence=1.0,
                justification="Perfect match",
                expected_title="Reentrancy vulnerability",
                found_title="Reentrancy vulnerability",
                dismissal_reasons=[]
            ),
            # First expected vs second found (already matched, won't be called)
            # Second expected vs first found (already used)
            # Second expected vs second found
            MatchResult(
                matched=False,
                confidence=0.3,
                justification="Different issue",
                expected_title="Missing validation",
                found_title="Integer overflow",
                dismissal_reasons=["different_root_cause"]
            ),
            MatchResult(
                matched=False,
                confidence=0.2,
                justification="Different issue",
                expected_title="Missing validation",
                found_title="Integer overflow",
                dismissal_reasons=["different_root_cause"]
            ),
        ]
        
        scorer = ScaBenchScorer({'api_key': 'test'})
        
        result = scorer.score_project(
            SAMPLE_BENCHMARK_DATA[0]['vulnerabilities'],
            SAMPLE_BASELINE_FINDINGS,
            "test_project"
        )
        
        assert result.total_expected == 2
        assert result.total_found == 2
        assert result.true_positives == 1  # Only confidence=1.0 counts
        assert result.false_negatives == 1
        assert result.false_positives == 1
        assert result.detection_rate == 0.5
        assert len(result.matched_findings) == 1
        assert len(result.missed_findings) == 1


class TestReportGenerator:
    """Test the report generator component."""
    
    def test_initialization(self):
        """Test ReportGenerator initialization."""
        config = {
            'tool_name': 'Test Tool',
            'tool_version': 'v2.0',
            'model': 'gpt-5'
        }
        generator = ReportGenerator(config)
        assert generator.scan_info['tool_name'] == 'Test Tool'
        assert generator.scan_info['tool_version'] == 'v2.0'
        assert generator.scan_info['model'] == 'gpt-5'
    
    def test_format_dismissal_reasons(self):
        """Test dismissal reason formatting."""
        generator = ReportGenerator()
        
        reasons = ['different_location', 'wrong_attack_vector']
        html = generator._format_dismissal_reasons(reasons)
        
        assert 'Wrong Location' in html
        assert 'Wrong Attack Vector' in html
        assert 'dismissal-badge' in html
    
    def test_generate_report_with_mock_data(self, tmp_path):
        """Test report generation with mock scoring data."""
        # Create mock scoring results
        scores_dir = tmp_path / "scores"
        scores_dir.mkdir()
        
        score_data = {
            "project": "test_project",
            "timestamp": "2024-01-01T00:00:00",
            "total_expected": 2,
            "total_found": 2,
            "true_positives": 1,
            "false_negatives": 1,
            "false_positives": 1,
            "detection_rate": 0.5,
            "precision": 0.5,
            "f1_score": 0.5,
            "matched_findings": [
                {
                    "expected": "Reentrancy vulnerability",
                    "matched": "Reentrancy in withdraw",
                    "confidence": 1.0,
                    "justification": "Perfect match",
                    "severity": "high"
                }
            ],
            "missed_findings": [
                {
                    "title": "Missing validation",
                    "severity": "low",
                    "reason": "Not detected"
                }
            ],
            "extra_findings": [
                {
                    "title": "Integer overflow",
                    "severity": "medium"
                }
            ],
            "potential_matches": []
        }
        
        score_file = scores_dir / "score_test_project.json"
        with open(score_file, 'w') as f:
            json.dump(score_data, f)
        
        # Generate report
        generator = ReportGenerator({
            'tool_name': 'Test Tool',
            'tool_version': 'v1.0',
            'model': 'gpt-4o'
        })
        
        output_file = tmp_path / "report.html"
        report_path = generator.generate_report(scores_dir, None, output_file)
        
        assert report_path.exists()
        
        # Check report content
        with open(report_path, 'r') as f:
            html = f.read()
        
        assert 'ScaBench Security Analysis Report' in html
        assert 'test_project' in html
        assert 'Reentrancy vulnerability' in html
        assert '50.0%' in html  # Detection rate
        assert 'Test Tool v1.0' in html


class TestIntegration:
    """Test the complete integration pipeline."""
    
    @patch('baseline_runner.OpenAI')
    @patch('scorer.OpenAI')
    def test_full_pipeline(self, mock_scorer_openai, mock_baseline_openai, tmp_path):
        """Test the complete flow from analysis to report."""
        
        # Setup mocks for baseline runner
        mock_baseline_client = Mock()
        mock_baseline_openai.return_value = mock_baseline_client
        
        mock_baseline_response = Mock()
        mock_baseline_response.choices = [Mock(message=Mock(content=json.dumps([
            {
                "title": "Reentrancy vulnerability in withdraw function",
                "description": "State update after external call",
                "vulnerability_type": "reentrancy",
                "severity": "high",
                "confidence": 0.95,
                "location": "withdraw() function"
            }
        ])))]
        mock_baseline_response.usage = Mock(prompt_tokens=100, completion_tokens=50)
        
        mock_baseline_client.chat.completions.create.return_value = mock_baseline_response
        
        # Setup mocks for scorer
        mock_scorer_client = Mock()
        mock_scorer_openai.return_value = mock_scorer_client
        
        mock_scorer_response = Mock()
        mock_scorer_response.choices = [Mock(message=Mock(content=json.dumps({
            "matched": True,
            "confidence": 1.0,
            "justification": "Perfect match",
            "dismissal_reasons": []
        })))]
        
        mock_scorer_client.chat.completions.create.return_value = mock_scorer_response
        
        # Step 1: Run baseline analysis
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        contract_file = source_dir / "VulnerableVault.sol"
        with open(contract_file, 'w') as f:
            f.write(SAMPLE_CONTRACT)
        
        runner = BaselineRunner({'api_key': 'test'})
        result = runner.analyze_project(
            "test_project",
            source_dir,
            max_files=10,
            file_patterns=["*.sol"]
        )
        
        assert result.total_findings == 1
        assert result.findings[0].severity == "high"
        
        # Save baseline results
        baseline_dir = tmp_path / "baseline_results"
        baseline_file = runner.save_result(result, baseline_dir)
        assert baseline_file.exists()
        
        # Step 2: Score the results
        scorer = ScaBenchScorer({'api_key': 'test'})
        
        # Load baseline results
        with open(baseline_file, 'r') as f:
            baseline_data = json.load(f)
        
        score_result = scorer.score_project(
            SAMPLE_BENCHMARK_DATA[0]['vulnerabilities'][:1],  # Just test with reentrancy
            baseline_data['findings'],
            "test_project"
        )
        
        assert score_result.true_positives == 1
        assert score_result.detection_rate == 1.0
        
        # Save scoring results
        scores_dir = tmp_path / "scores"
        score_file = scorer.save_result(score_result, scores_dir)
        assert score_file.exists()
        
        # Step 3: Generate report
        generator = ReportGenerator({
            'tool_name': 'Integration Test',
            'tool_version': 'v1.0'
        })
        
        report_file = tmp_path / "report.html"
        report_path = generator.generate_report(scores_dir, None, report_file)
        
        assert report_path.exists()
        
        # Verify report content
        with open(report_path, 'r') as f:
            html = f.read()
        
        assert 'test_project' in html
        assert 'True Positives' in html
        assert '100.0%' in html  # Detection rate


def test_cli_integration(tmp_path, monkeypatch):
    """Test command-line interface integration."""
    import subprocess
    
    # Create test data
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    contract_file = source_dir / "Test.sol"
    with open(contract_file, 'w') as f:
        f.write(SAMPLE_CONTRACT)
    
    benchmark_file = tmp_path / "benchmark.json"
    with open(benchmark_file, 'w') as f:
        json.dump(SAMPLE_BENCHMARK_DATA, f)
    
    # Mock environment variable
    monkeypatch.setenv("OPENAI_API_KEY", "test_key")
    
    # Note: In real tests, you would test the actual CLI
    # This is a placeholder showing the intended flow
    assert True  # Placeholder


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])