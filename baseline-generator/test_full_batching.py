#!/usr/bin/env python3
"""Test the full batching system with mock LLM calls"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from baseline_runner import SourceFileAnalyzer, Finding
from pathlib import Path
import tempfile
import shutil
from unittest.mock import MagicMock, patch
import json

def create_test_project_large():
    """Create a temporary project with many files to trigger batching"""
    temp_dir = tempfile.mkdtemp()
    
    # Create src directory with 55 contracts (should trigger batching)
    src_dir = Path(temp_dir) / "src"
    src_dir.mkdir()
    
    for i in range(55):
        contract_file = src_dir / f"Contract{i}.sol"
        contract_file.write_text(f"""
pragma solidity ^0.8.0;

contract Contract{i} {{
    uint256 public value = {i};
    
    function setValue(uint256 _value) public {{
        value = _value;  // Potential reentrancy
    }}
}}
""")
    
    return temp_dir

def test_analyze_project_with_batching():
    """Test the full analyze_project method with batching"""
    print("Testing analyze_project with batching...")
    
    temp_dir = create_test_project_large()
    
    try:
        # Mock the OpenAI client
        with patch('openai.OpenAI') as mock_openai:
            # Create mock response
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({
                "findings": [
                    {
                        "file_path": "src/Contract0.sol",
                        "severity": "medium",
                        "title": "Test vulnerability",
                        "description": "This is a test finding.",
                        "confidence": 0.8
                    }
                ]
            })
            
            # Setup mock client
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            # Create analyzer
            analyzer = SourceFileAnalyzer(model="gpt-4", api_key="test_key")
            
            # Analyze project
            findings = analyzer.analyze_project(Path(temp_dir))
            
            # Check that batching was used
            print(f"API calls made: {mock_client.chat.completions.create.call_count}")
            print(f"Findings returned: {len(findings)}")
            
            # With 55 files and batch size of 10, we expect 6 batches
            expected_batches = 6
            actual_calls = mock_client.chat.completions.create.call_count
            
            if actual_calls == expected_batches:
                print(f"✅ Batching worked correctly: {actual_calls} API calls for 55 files")
                return True
            else:
                print(f"❌ Expected {expected_batches} API calls, got {actual_calls}")
                return False
            
    finally:
        shutil.rmtree(temp_dir)

def test_analyze_project_without_batching():
    """Test that small projects don't use batching"""
    print("\nTesting analyze_project without batching (small project)...")
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Create only 5 files (should not trigger batching)
        src_dir = Path(temp_dir) / "src"
        src_dir.mkdir()
        
        for i in range(5):
            contract_file = src_dir / f"Contract{i}.sol"
            contract_file.write_text(f"contract Contract{i} {{}}")
        
        # Mock the OpenAI client
        with patch('openai.OpenAI') as mock_openai:
            # Create mock response
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({"findings": []})
            
            # Setup mock client
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            # Create analyzer
            analyzer = SourceFileAnalyzer(model="gpt-4", api_key="test_key")
            
            # Analyze project
            findings = analyzer.analyze_project(Path(temp_dir))
            
            # Check that individual analysis was used (5 calls for 5 files)
            actual_calls = mock_client.chat.completions.create.call_count
            
            if actual_calls == 5:
                print(f"✅ Individual analysis used correctly: {actual_calls} API calls for 5 files")
                return True
            else:
                print(f"❌ Expected 5 API calls, got {actual_calls}")
                return False
            
    finally:
        shutil.rmtree(temp_dir)

if __name__ == "__main__":
    print("=== Testing Full Batching System ===\n")
    
    # Test with large project (batching)
    batching_test = test_analyze_project_with_batching()
    
    # Test with small project (no batching)
    no_batching_test = test_analyze_project_without_batching()
    
    if batching_test and no_batching_test:
        print("\n✅ All integration tests passed!")
    else:
        print("\n❌ Some integration tests failed!")
        sys.exit(1)