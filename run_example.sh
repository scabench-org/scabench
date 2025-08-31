#!/bin/bash
#
# Example end-to-end pipeline for ScaBench tooling
# This script demonstrates the complete flow from analysis to report generation
#

set -e  # Exit on error

echo "==================================="
echo "ScaBench End-to-End Pipeline Demo"
echo "==================================="

# Check for OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY environment variable not set"
    echo "Please set it with: export OPENAI_API_KEY='your-key-here'"
    exit 1
fi

# Create test directories
echo "Setting up test environment..."
mkdir -p test_data/source
mkdir -p test_data/results

# Create a sample vulnerable contract
cat > test_data/source/VulnerableVault.sol << 'EOF'
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
    
    // Integer overflow protection (but showing pattern)
    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }
    
    // Missing access control
    function emergencyWithdraw(address to, uint256 amount) external {
        // Bug: No access control
        payable(to).transfer(amount);
    }
}
EOF

# Create sample benchmark data
cat > test_data/benchmark.json << 'EOF'
[
  {
    "project_id": "test_vulnerable_vault",
    "name": "Test Vulnerable Vault",
    "vulnerabilities": [
      {
        "title": "Reentrancy vulnerability in withdraw function",
        "description": "The withdraw function updates state after making an external call",
        "vulnerability_type": "reentrancy",
        "severity": "high",
        "location": "withdraw() function"
      },
      {
        "title": "Missing access control in emergencyWithdraw",
        "description": "The emergencyWithdraw function has no access restrictions",
        "vulnerability_type": "access control",
        "severity": "critical",
        "location": "emergencyWithdraw() function"
      }
    ]
  }
]
EOF

echo "Test environment ready!"
echo ""

# Step 1: Run baseline analysis
echo "Step 1: Running baseline analysis..."
echo "--------------------------------------"
python baseline-runner/baseline_runner.py \
    --project test_vulnerable_vault \
    --source test_data/source \
    --output test_data/results/baseline \
    --model gpt-4o-mini

echo ""
echo "Baseline analysis complete!"
echo ""

# Step 2: Score the results
echo "Step 2: Scoring results against benchmark..."
echo "---------------------------------------------"
python scoring/scorer.py \
    --benchmark test_data/benchmark.json \
    --results test_data/results/baseline/baseline_test_vulnerable_vault.json \
    --output test_data/results/scores \
    --model gpt-4o-mini \
    --verbose

echo ""
echo "Scoring complete!"
echo ""

# Step 3: Generate HTML report
echo "Step 3: Generating HTML report..."
echo "----------------------------------"
python scoring/report_generator.py \
    --scores test_data/results/scores \
    --output test_data/results/report.html \
    --tool-name "ScaBench Demo" \
    --tool-version "v1.0" \
    --model gpt-4o-mini

echo ""
echo "==================================="
echo "Pipeline Complete!"
echo "==================================="
echo ""
echo "Results:"
echo "- Baseline results: test_data/results/baseline/"
echo "- Scoring results: test_data/results/scores/"
echo "- HTML Report: test_data/results/report.html"
echo ""
echo "Open the HTML report in your browser to view the results:"
echo "  open test_data/results/report.html  # macOS"
echo "  xdg-open test_data/results/report.html  # Linux"
echo ""