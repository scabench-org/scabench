# ScaBench Official Tooling Documentation

Complete guide for using ScaBench tools to evaluate smart contract security analyzers.

## Purpose

ScaBench provides:
1. **Benchmark Dataset** - Real vulnerabilities from audits (31 projects, 555 vulns)
2. **Source Code** - Exact commits for reproducible analysis
3. **Baseline Implementation** - Reference analyzer using LLMs
4. **Evaluation Tools** - Score any tool against the benchmark

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd benchmarks/scabench

# Install dependencies
pip install -r requirements.txt

# Set up your OpenAI API key
export OPENAI_API_KEY="your-api-key-here"
```

## Quick Start - Process ALL Projects

```bash
# One command to run everything
./run_all.sh
```

This will:
1. Download all 31 projects from the dataset
2. Run baseline security analysis on each
3. Score all results against the benchmark
4. Generate comprehensive HTML reports

## Component Usage

### 1. Download Source Code

```bash
# Get all projects at exact commits
python dataset-generator/checkout_sources.py \
    --dataset datasets/curated-2025-08-18.json \
    --output sources/

# Get specific project
python dataset-generator/checkout_sources.py \
    --project vulnerable_vault
```

### 2. Run Baseline Analysis

```bash
# Analyze a project
python baseline-runner/baseline_runner.py \
    --project my_project \
    --source sources/my_project \
    --output baseline_results/
```

### 3. Score Results

```bash
# Score your tool's results
python scoring/scorer.py \
    --benchmark datasets/curated-2025-08-18.json \
    --results your_results.json \
    --output scores/
```

### 4. Generate Report

```bash
python scoring/report_generator.py \
    --scores scores/ \
    --output report.html
```

## Using ScaBench with Your Own Tool

### Step 1: Get Source Code
```bash
python dataset-generator/checkout_sources.py
```

### Step 2: Run Your Tool
Analyze each project in `sources/` with your security tool.

### Step 3: Format Your Output
Create JSON files matching this structure:
```json
{
  "project": "project_name",
  "timestamp": "2024-01-01T00:00:00",
  "findings": [
    {
      "title": "Reentrancy vulnerability",
      "description": "State updated after external call...",
      "vulnerability_type": "reentrancy",
      "severity": "high",
      "location": "withdraw() function",
      "file": "Vault.sol"
    }
  ]
}
```

### Step 4: Score Against Benchmark
```bash
python scoring/scorer.py \
    --benchmark datasets/curated-2025-08-18.json \
    --results-dir your_results/
```

### Step 5: Generate Report
```bash
python scoring/report_generator.py \
    --scores scores/ \
    --output your_tool_report.html \
    --tool-name "Your Tool Name"
```

## Configuration

Copy `config.example.json` to `config.json` and customize:

```json
{
  "baseline_runner": {
    "model": "gpt-5-mini",
    "max_files_per_project": 50,
    "output_dir": "baseline_results"
  },
  "scorer": {
    "model": "gpt-4o",
    "strict_matching": true,
    "confidence_threshold": 1.0
  },
  "report_generator": {
    "tool_name": "ScaBench Baseline",
    "tool_version": "v1.0"
  }
}
```

## Strict Matching Policy

The scorer uses EXTREMELY STRICT matching criteria:

- **IDENTICAL LOCATION** - Must be EXACT same file/contract/function
- **EXACT IDENTIFIERS** - Same contract names, function names, variables
- **IDENTICAL ROOT CAUSE** - Must be THE SAME vulnerability
- **IDENTICAL ATTACK VECTOR** - Exact same exploitation method
- **IDENTICAL IMPACT** - Exact same security consequence
- **NO MATCH** for similar patterns in different locations
- **NO MATCH** for same bug type but different functions
- **WHEN IN DOUBT: DO NOT MATCH**

Only findings with confidence = 1.0 count as true positives.

## Testing

Run the test suite with mock LLM calls:

```bash
# Install test dependencies
pip install pytest pytest-mock pytest-cov

# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=baseline_runner --cov=scoring

# Run specific test
pytest tests/test_integration.py::TestBaselineRunner -v
```

## Output Formats

### Baseline Results Format

```json
{
  "project": "project_name",
  "timestamp": "2024-01-01T00:00:00",
  "files_analyzed": 10,
  "files_skipped": 2,
  "total_findings": 5,
  "findings": [
    {
      "title": "Reentrancy vulnerability",
      "description": "Detailed description...",
      "vulnerability_type": "reentrancy",
      "severity": "high",
      "confidence": 0.95,
      "location": "withdraw() function",
      "file": "Vault.sol",
      "id": "unique_id"
    }
  ],
  "token_usage": {
    "input_tokens": 1000,
    "output_tokens": 500,
    "total_tokens": 1500
  }
}
```

### Scoring Results Format

```json
{
  "project": "project_name",
  "timestamp": "2024-01-01T00:00:00",
  "total_expected": 10,
  "total_found": 8,
  "true_positives": 6,
  "false_negatives": 4,
  "false_positives": 2,
  "detection_rate": 0.6,
  "precision": 0.75,
  "f1_score": 0.67,
  "matched_findings": [...],
  "missed_findings": [...],
  "extra_findings": [...],
  "potential_matches": [...]
}
```

## Models Supported

- **GPT-5** and **GPT-5-mini** (recommended for baseline analysis)
- **GPT-4o** and **GPT-4o-mini** (recommended for scoring)
- Other OpenAI models (gpt-4, gpt-3.5-turbo, etc.)

## Performance Tips

1. **File Selection**: Use `--max-files` to limit analysis during testing
2. **Model Choice**: 
   - Use GPT-5-mini for fast baseline analysis
   - Use GPT-4o for accurate scoring/matching
3. **Batch Processing**: Process multiple projects using shell scripts
4. **Caching**: Results are saved to disk for reprocessing

## Troubleshooting

### Common Issues

1. **API Key Error**: Ensure `OPENAI_API_KEY` is set correctly
2. **File Not Found**: Check source paths are absolute or relative to current directory
3. **No Matches Found**: Review the strict matching policy - only perfect matches count
4. **Rate Limits**: Add delays between API calls if hitting rate limits

### Debug Mode

Enable verbose output for debugging:

```bash
# Baseline runner - shows detailed analysis
python baseline-runner/baseline_runner.py ... --verbose

# Scorer - shows matching justifications
python scoring/scorer.py ... --verbose
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

See LICENSE file in the repository root.

## Support

For issues or questions:
- Open an issue on GitHub
- Check the documentation at https://github.com/scabench
- Review test cases for usage examples