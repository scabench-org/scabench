# ScaBench: How It Works

## Overview

ScaBench is a benchmark for evaluating smart contract security tools. It consists of:

1. **Curated Datasets** - Real vulnerabilities from audits
2. **Source Code** - Actual smart contracts at specific commits  
3. **Baseline Tools** - Reference implementation for comparison
4. **Scoring System** - Evaluation with LLM-based matching

## Components Explained

### 1. Dataset Generator (`dataset-generator/`)

**Purpose**: Create new benchmark datasets from audit platforms

```bash
cd dataset-generator
python scraper.py --platforms code4rena cantina sherlock --months 3
```

This scrapes recent audits and creates a JSON dataset with:
- Project metadata
- Repository URLs and commit hashes
- Vulnerability descriptions and locations

### 2. Official Datasets (`datasets/`)

**Current Dataset**: `curated-2025-08-18.json`
- 31 projects carefully selected
- 555 real vulnerabilities 
- 114 high/critical severity
- From Code4rena, Cantina, and Sherlock

Dataset format:
```json
{
  "project_id": "vulnerable_vault",
  "name": "Vulnerable Vault Protocol",
  "codebases": [{
    "repo_url": "https://github.com/...",
    "commit": "abc123..."
  }],
  "vulnerabilities": [{
    "title": "Reentrancy in withdraw",
    "severity": "high",
    "description": "...",
    "location": "withdraw() function"
  }]
}
```

### 3. Source Code Checkout (`dataset-generator/checkout_sources.py`)

**Purpose**: Download exact source code for analysis

```bash
# Download ALL projects from dataset
python dataset-generator/checkout_sources.py \
  --dataset datasets/curated-2025-08-18.json \
  --output sources/

# Download specific project
python dataset-generator/checkout_sources.py \
  --project vulnerable_vault \
  --output sources/
```

This ensures everyone analyzes the EXACT same code (same commits).

### 4. Baseline Runner (`baseline-runner/`)

**Purpose**: Reference security analyzer using LLMs

```bash
python baseline-runner/baseline_runner.py \
  --project my_project \
  --source sources/my_project \
  --output baseline_results/
```

Output format (what YOUR tool should produce):
```json
{
  "project": "vulnerable_vault",
  "timestamp": "2024-01-01T00:00:00",
  "files_analyzed": 10,
  "total_findings": 5,
  "findings": [{
    "title": "Reentrancy vulnerability",
    "description": "State change after external call...",
    "vulnerability_type": "reentrancy",
    "severity": "high",
    "confidence": 0.95,
    "location": "withdraw() function",
    "file": "Vault.sol"
  }]
}
```

### 5. Scoring Tool (`scoring/`)

**Purpose**: Compare any tool's findings against the benchmark

```bash
python scoring/scorer.py \
  --benchmark datasets/curated-2025-08-18.json \
  --results your_tool_results.json \
  --output scores/
```

Uses GPT-5-mini to match findings with strict criteria:
- Must be exact same vulnerability
- Same location, root cause, and impact
- Only confidence = 1.0 counts as true positive

### 6. Report Generator (`scoring/report_generator.py`)

**Purpose**: Create HTML reports with visualizations

```bash
python scoring/report_generator.py \
  --scores scores/ \
  --output report.html
```

## Complete Workflows

### Running the Official Baseline

**Easy way - Process ALL projects:**
```bash
./run_all.sh
```

This single command:
1. Downloads all source code
2. Runs baseline analysis
3. Scores against benchmark
4. Generates reports

**Manual way - Step by step:**
```bash
# 1. Download sources
python dataset-generator/checkout_sources.py

# 2. Run baseline
python baseline-runner/baseline_runner.py --project X --source sources/X

# 3. Score results
python scoring/scorer.py --benchmark datasets/curated-2025-08-18.json --results baseline_results/

# 4. Generate report
python scoring/report_generator.py --scores scores/
```

## Using ScaBench with YOUR Tool

### Step 1: Download Source Code

```bash
# Get all project sources at exact commits
python dataset-generator/checkout_sources.py \
  --dataset datasets/curated-2025-08-18.json \
  --output sources/
```

### Step 2: Run YOUR Security Tool

Analyze each project in `sources/` with your tool.

### Step 3: Format Your Results

Create a JSON file matching this format for EACH project:

```json
{
  "project": "project_name",
  "timestamp": "2024-01-01T00:00:00",
  "files_analyzed": 10,
  "files_skipped": 0,
  "total_findings": 5,
  "findings": [
    {
      "title": "Clear description of vulnerability",
      "description": "Detailed explanation...",
      "vulnerability_type": "reentrancy|access control|integer overflow|etc",
      "severity": "critical|high|medium|low",
      "confidence": 0.0-1.0,
      "location": "function_name() or line reference",
      "file": "Contract.sol"
    }
  ],
  "token_usage": {
    "input_tokens": 1000,
    "output_tokens": 500,
    "total_tokens": 1500
  }
}
```

**Required fields for each finding:**
- `title`: Short, clear vulnerability description
- `description`: Detailed explanation
- `vulnerability_type`: Category of issue
- `severity`: critical/high/medium/low
- `location`: Where it occurs (function/line)
- `file`: Source file name

**Optional fields:**
- `confidence`: Your tool's confidence (0.0-1.0)
- `token_usage`: If using LLMs

### Step 4: Score Your Results

```bash
# Single project
python scoring/scorer.py \
  --benchmark datasets/curated-2025-08-18.json \
  --results your_results/project_name.json \
  --output scores/

# All projects
python scoring/scorer.py \
  --benchmark datasets/curated-2025-08-18.json \
  --results-dir your_results/ \
  --output scores/
```

### Step 5: Generate Report

```bash
python scoring/report_generator.py \
  --scores scores/ \
  --output your_tool_report.html \
  --tool-name "Your Tool Name" \
  --tool-version "v1.0"
```

## Example: Evaluating a Custom Tool

```bash
# 1. Get the code
python dataset-generator/checkout_sources.py

# 2. Run your tool (example with mythril)
for project in sources/*; do
  mythril analyze "$project/**/*.sol" > "my_results/$(basename $project).json"
done

# 3. Convert to required format (you need to write this)
python convert_mythril_output.py my_results/ formatted_results/

# 4. Score against benchmark
python scoring/scorer.py \
  --benchmark datasets/curated-2025-08-18.json \
  --results-dir formatted_results/ \
  --output scores/

# 5. View results
python scoring/report_generator.py --scores scores/ --output mythril_report.html
open mythril_report.html
```

## Metrics Explained

- **Detection Rate (Recall)**: What % of real vulnerabilities did you find?
- **Precision**: What % of your findings were real vulnerabilities?
- **F1 Score**: Harmonic mean of precision and recall
- **True Positives**: Correctly identified vulnerabilities
- **False Negatives**: Missed vulnerabilities
- **False Positives**: Reported non-existent vulnerabilities

## Tips for Tool Developers

1. **Use exact commits**: Always analyze code from `checkout_sources.py`
2. **Be specific**: Vague findings won't match
3. **Include location**: Must specify function/contract/line
4. **Match severity**: Use standard levels (critical/high/medium/low)
5. **Test small first**: Use `--max-files 5` for quick tests

## Directory Structure After Running

```
benchmarks/scabench/
├── sources/                    # Downloaded code (git ignored)
│   ├── vulnerable_vault/
│   ├── safe_protocol/
│   └── ...
├── baseline_results/           # Baseline findings (git ignored)
├── your_tool_results/          # Your findings (git ignored)
├── scores/                     # Scoring results (git ignored)
└── reports/                    # HTML reports (git ignored)
```

All generated data is git-ignored to keep the repo clean!