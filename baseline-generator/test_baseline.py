#!/usr/bin/env python3
"""
Test script for the baseline generator.
Creates a minimal test dataset and runs the baseline analysis.
"""

import json
import tempfile
import os
from pathlib import Path
from datetime import datetime

def create_test_dataset():
    """Create a minimal test dataset"""
    dataset = {
        "dataset_id": "test_dataset",
        "description": "Test dataset for baseline generator",
        "created_at": datetime.now().isoformat(),
        "projects": [
            {
                "project_id": "test_project_1",
                "name": "Test Solidity Project",
                "platform": "test",
                "codebases": [
                    {
                        "codebase_id": "test_codebase_1",
                        "repo_url": "https://github.com/OpenZeppelin/openzeppelin-contracts",
                        "commit": "v4.9.0",
                        "tree_url": "",
                        "tarball_url": ""
                    }
                ],
                "vulnerabilities": [
                    {
                        "finding_id": "test_vuln_1",
                        "severity": "high",
                        "title": "Test vulnerability",
                        "description": "This is a test vulnerability"
                    }
                ]
            }
        ]
    }
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(dataset, f, indent=2)
        return f.name

def main():
    # Check for API key
    if not os.getenv('OPENAI_API_KEY'):
        print("Warning: OPENAI_API_KEY not set. Test will fail during LLM calls.")
        print("Set it with: export OPENAI_API_KEY=your_key_here")
    
    # Create test dataset
    print("Creating test dataset...")
    dataset_file = create_test_dataset()
    print(f"Test dataset created: {dataset_file}")
    
    # Create output directory
    output_dir = Path("test_output")
    output_dir.mkdir(exist_ok=True)
    
    # Run baseline generator
    print("\nRunning baseline generator...")
    print("Note: This will analyze real OpenZeppelin contracts as a test.")
    print("Use --max-files 1 to limit the analysis to just one file.\n")
    
    import sys
    sys.argv = [
        'baseline_runner.py',
        dataset_file,
        '--output-dir', str(output_dir),
        '--max-files', '1',  # Analyze only 1 file for testing
        '--verbose'
    ]
    
    try:
        # Import and run the baseline runner
        from baseline_runner import main as run_baseline
        run_baseline()
        
        print(f"\nTest complete! Check results in: {output_dir}")
        
        # Check if output files were created
        output_files = list(output_dir.glob('*.json'))
        if output_files:
            print(f"Generated files: {[f.name for f in output_files]}")
            
            # Show a sample of the results
            baseline_file = output_dir / "test_project_1_baseline.json"
            if baseline_file.exists():
                with open(baseline_file, 'r') as f:
                    data = json.load(f)
                    print(f"\nAnalysis results:")
                    print(f"  - Findings count: {data['findings_count']}")
                    if data['findings']:
                        print(f"  - Sample finding: {data['findings'][0]['title']}")
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        os.unlink(dataset_file)
        print(f"\nCleaned up test dataset: {dataset_file}")

if __name__ == '__main__':
    main()