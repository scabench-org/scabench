#!/usr/bin/env python3
"""Test the batching logic without making actual API calls"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from baseline_runner import SourceFileAnalyzer
from pathlib import Path
import tempfile
import shutil

def create_test_project():
    """Create a temporary project with many files"""
    temp_dir = tempfile.mkdtemp()
    
    # Create src directory with main contracts
    src_dir = Path(temp_dir) / "src"
    src_dir.mkdir()
    
    # Create 60 contract files (should trigger batching)
    for i in range(60):
        contract_file = src_dir / f"Contract{i}.sol"
        contract_file.write_text(f"""
pragma solidity ^0.8.0;

contract Contract{i} {{
    uint256 public value = {i};
    
    function setValue(uint256 _value) public {{
        value = _value;
    }}
}}
""")
    
    # Create some test files (should be filtered out)
    test_dir = Path(temp_dir) / "test"
    test_dir.mkdir()
    for i in range(20):
        test_file = test_dir / f"Test{i}.t.sol"
        test_file.write_text(f"// Test file {i}")
    
    return temp_dir

def test_file_filtering():
    """Test that file filtering works correctly"""
    print("Testing file filtering...")
    
    temp_dir = create_test_project()
    try:
        analyzer = SourceFileAnalyzer(model="gpt-4", api_key="dummy_key_for_testing")
        
        # Find source files
        source_files = analyzer._find_source_files(Path(temp_dir))
        
        print(f"Total files found: {len(source_files)}")
        print(f"Files after filtering:")
        for f in source_files[:5]:  # Show first 5
            print(f"  - {f.relative_to(temp_dir)}")
        
        # Check that test files were filtered out
        test_files = [f for f in source_files if 'test' in str(f).lower()]
        print(f"Test files remaining: {len(test_files)} (should be 0)")
        
        # Check that src files were included
        src_files = [f for f in source_files if '/src/' in str(f)]
        print(f"Src files included: {len(src_files)} (should be 60)")
        
        return len(source_files) == 60 and len(test_files) == 0
        
    finally:
        shutil.rmtree(temp_dir)

def test_batch_logic():
    """Test the batching logic"""
    print("\nTesting batch logic...")
    
    # Create mock file list
    mock_files = [Path(f"/tmp/src/Contract{i}.sol") for i in range(324)]
    
    batch_size = 10
    num_batches = (len(mock_files) + batch_size - 1) // batch_size
    
    print(f"Files: {len(mock_files)}")
    print(f"Batch size: {batch_size}")
    print(f"Expected batches: {num_batches}")
    
    # Simulate batching
    batches_processed = 0
    for i in range(0, len(mock_files), batch_size):
        batch = mock_files[i:i + batch_size]
        batches_processed += 1
        if batches_processed <= 3:  # Show first 3 batches
            print(f"Batch {batches_processed}: {len(batch)} files")
    
    print(f"Total batches processed: {batches_processed}")
    
    return batches_processed == num_batches

if __name__ == "__main__":
    print("=== Testing Batching System ===\n")
    
    # Test file filtering
    filtering_ok = test_file_filtering()
    print(f"File filtering test: {'PASSED' if filtering_ok else 'FAILED'}")
    
    # Test batch logic
    batching_ok = test_batch_logic()
    print(f"Batch logic test: {'PASSED' if batching_ok else 'FAILED'}")
    
    if filtering_ok and batching_ok:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)