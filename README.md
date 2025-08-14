# SCABench
A framework for evaluating AI code analysis contract audit agents using recent real-world data.

- Easily compile fresh eval datasets (codebase -> vulnerabilities) from multiple sources
- Run baseline LLM analysis to establish performance benchmarks
- Automatically evaluate and compare results

## Components

### 1. Dataset Generator
A comprehensive scraper system for extracting security audit data from multiple platforms.

- **Location**: [`/dataset-generator`](./dataset-generator)
- **Purpose**: Collects vulnerability findings, GitHub repositories, and project metadata from Code4rena, Cantina, and Sherlock
- **Features**: 
  - Multi-platform support with 100% extraction accuracy
  - GitHub integration for repository and commit tracking
  - Flexible date filtering and test mode
  - Produces structured JSON datasets for AI training/evaluation

See the [dataset-generator README](./dataset-generator/README.md) for detailed usage instructions.

### 2. Baseline Generator
An LLM-based security analysis tool that establishes baseline performance metrics for vulnerability detection.

- **Location**: [`/baseline-generator`](./baseline-generator)
- **Purpose**: Analyzes codebases using GPT-4o to find vulnerabilities and evaluates performance against expected findings
- **Features**:
  - Automatic repository downloading and caching
  - Multi-language support (Solidity, Rust, Go, Python, etc.)
  - Session management for resuming interrupted runs
  - Comprehensive evaluation system with found/missed/false positive metrics
  - Detailed debugging output for investigating results

See the [baseline-generator README](./baseline-generator/README.md) for detailed usage instructions.

## Quick Start

### 1. Generate Dataset
```bash
cd dataset-generator
python scraper.py --months 3 --output datasets/recent_audits.json
```

### 2. Run Baseline Analysis
```bash
cd ../baseline-generator
export OPENAI_API_KEY=your_key_here
python baseline_runner.py ../dataset-generator/datasets/recent_audits.json \
  --output-dir results \
  --max-files 10
```

### 3. Evaluate Performance
```bash
python evaluate_baseline.py results ../dataset-generator/datasets/recent_audits.json
```

## Complete Workflow Example

```bash
# Step 1: Scrape recent audit data (last 3 months)
cd dataset-generator
python scraper.py --platforms code4rena cantina sherlock --months 3

# Step 2: Run baseline on specific projects
cd ../baseline-generator
export OPENAI_API_KEY=sk-...
python baseline_runner.py ../dataset-generator/datasets/scabench_*.json \
  --project "BitVault" \
  --max-files 10 \
  --output-dir baseline_results

# Step 3: Evaluate how well the baseline performed
python evaluate_baseline.py baseline_results ../dataset-generator/datasets/scabench_*.json

# Step 4: Check the results
cat baseline_results/evaluation/evaluation_summary.json | jq '.overall_metrics'
```

### Expected Output
```json
{
  "total_found": 12,
  "total_missed": 22,
  "total_false_positives": 8,
  "overall_recall": "35.3%"
}
```

## Performance Metrics

The framework evaluates AI agents using three key metrics:

1. **Found Issues**: Vulnerabilities correctly identified (true positives)
2. **Missed Issues**: Expected vulnerabilities not detected (false negatives)  
3. **False Positives**: Detected issues that don't match any expected vulnerability

### Severity-Based Scoring
- Tracks performance separately for High, Medium, and Low severity issues
- Ignores informational findings
- Provides detailed breakdown per project and overall

## Directory Structure

```
ai-auditor-eval/
├── dataset-generator/       # Scrapes audit data from platforms
│   ├── scrapers/           # Platform-specific scrapers
│   ├── datasets/           # Generated JSON datasets
│   └── test/              # Test files
├── baseline-generator/      # LLM-based baseline analysis
│   ├── session_manager.py  # Resume interrupted runs
│   ├── evaluate_baseline.py # Compare against expected
│   └── results/           # Analysis outputs
└── datasets/               # Shared dataset storage
```

## Requirements

- Python 3.8+
- OpenAI API key (for baseline generator)
- Internet connection (for scraping and downloading repos)

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/ai-auditor-eval.git
cd ai-auditor-eval

# Install dataset generator dependencies
cd dataset-generator
pip install -r requirements.txt

# Install baseline generator dependencies  
cd ../baseline-generator
pip install -r requirements.txt
```

## Contributing

Contributions are welcome! Please see the individual component READMEs for detailed development guidelines.

## License

MIT License - see LICENSE file for details
