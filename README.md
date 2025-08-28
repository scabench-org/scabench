# ScaBench: Smart Contract Audit Benchmark

A comprehensive framework for evaluating security analysis tools and AI agents on real-world smart contract vulnerabilities. ScaBench provides curated datasets from recent audits and official tooling for consistent evaluation.

> **🎉 NEW: Run ALL 31 projects with one command!**
> ```bash
> ./run_all.sh  # Downloads sources, analyzes, scores, and generates reports
> ```

## 📚 Key Documents

- **[HOW IT WORKS](./HOW_IT_WORKS.md)** - Detailed explanation of all components
- **[QUICK START](./QUICK_START.md)** - Get running in 2 minutes
- **[DATASET INFO](./datasets/README.md)** - Dataset format and statistics
- **[TOOLING README](./TOOLING_README.md)** - Complete tool documentation

## Features

- 🎯 **Curated Datasets**: Real-world vulnerabilities from Code4rena, Cantina, and Sherlock audits
- 🤖 **Baseline Runner**: LLM-based security analyzer with configurable models
- 📊 **Scoring Tool**: Evaluates findings with LLM-based matching (confidence = 1.0 only)
- 📈 **Report Generator**: HTML reports with visualizations and performance metrics
- 🔄 **Pipeline Automation**: Complete workflow with single-command execution

## Available Curated Datasets

| Dataset | Report | Time Range | Projects | Vulnerabilities | High/Critical | Total LoC | Solidity LoC |
|---------|--------|------------|----------|-----------------|---------------|-----------|--------------|
| [curated-2025-08-18.json](./datasets/curated-2025-08-18.json) | [Report](./datasets/curated-2025-08-18.md) | 2024-08 to 2025-08 | **31** | **555** | **114** | 3.3M | 267K |

**Dataset Statistics:**
- **Source**: 269 original projects filtered to 31 high-quality projects
- **Platforms**: Code4rena, Cantina, and Sherlock
- **Languages**: Solidity, Rust, Go, TypeScript, Move, Cairo
- **Curation Criteria**: 
  - Accessible GitHub repositories
  - ≥5 vulnerabilities per project
  - ≥1 high/critical severity finding
  - Recent audits (2024-2025)

## What Each Component Does

### 📊 **Official Datasets** (`datasets/`)
Pre-curated benchmark datasets with real vulnerabilities from audits.
- **Current**: `curated-2025-08-18.json` (31 projects, 555 vulnerabilities)
- Format: JSON with project metadata, repo URLs, commits, and vulnerability details
- [View dataset documentation](./datasets/)

### 🔧 **Dataset Generator** (`dataset-generator/`)
Create NEW datasets by scraping audit platforms.
```bash
cd dataset-generator
python scraper.py --platforms code4rena cantina sherlock --months 3
```

### 📥 **Source Checkout** (`dataset-generator/checkout_sources.py`)
Download project source code at EXACT commits from dataset.
```bash
# Download all projects
python dataset-generator/checkout_sources.py

# Download specific project
python dataset-generator/checkout_sources.py --project vulnerable_vault
```

### 🔍 **Baseline Runner** (`baseline-runner/`)
Reference security analyzer using LLMs. Produces findings in standard JSON format.
```bash
python baseline-runner/baseline_runner.py \
  --project my_project \
  --source sources/my_project
```

### 📈 **Scorer** (`scoring/scorer.py`)
Evaluates ANY tool's findings against the benchmark using LLM matching.
```bash
python scoring/scorer.py \
  --benchmark datasets/curated-2025-08-18.json \
  --results your_tool_results.json
```

### 📄 **Report Generator** (`scoring/report_generator.py`)
Creates HTML reports with metrics and visualizations.
```bash
python scoring/report_generator.py \
  --scores scores/ \
  --output report.html
```

## Quick Start

### Prerequisites
```bash
# Install dependencies
pip install -r requirements.txt

# Set OpenAI API key
export OPENAI_API_KEY="your-key-here"
```

### Option 1: Process ALL Projects (Easiest!) 🚀
```bash
# Run everything for ALL 31 projects with one command
./run_all.sh

# Or limit files for faster testing
./run_all.sh --max-files 10
```

This will automatically:
1. Download all project sources at correct commits
2. Run baseline analysis on each project
3. Score all results against the benchmark
4. Generate comprehensive reports

### Option 2: Process Single Project
```bash
# For a specific project
./run_pipeline.sh --project vulnerable_vault --source sources/vulnerable_vault
```

### Option 3: Step-by-Step Manual Process

## Two Ways to Use ScaBench

### 🎯 Option A: Run the Official Baseline

**Easiest - Process ALL projects with one command:**
```bash
./run_all.sh
```

This automatically:
1. Downloads all source code at exact commits
2. Runs baseline security analysis
3. Scores against benchmark
4. Generates comprehensive reports

**Manual approach for specific projects:**
```bash
# 1. Download source code
python dataset-generator/checkout_sources.py --project vulnerable_vault

# 2. Run baseline analysis
python baseline-runner/baseline_runner.py \
  --project vulnerable_vault \
  --source sources/vulnerable_vault

# 3. Score results
python scoring/scorer.py \
  --benchmark datasets/curated-2025-08-18.json \
  --results baseline_results/baseline_vulnerable_vault.json

# 4. Generate report
python scoring/report_generator.py \
  --scores scores/ \
  --output report.html
```

### 🚀 Option B: Evaluate YOUR Tool

**Step 1: Get the source code**
```bash
python dataset-generator/checkout_sources.py \
  --dataset datasets/curated-2025-08-18.json \
  --output sources/
```

**Step 2: Run YOUR tool on each project**
```bash
# Example with your tool
your-tool analyze sources/project1/ > results/project1.json
```

**Step 3: Format results to match required JSON structure**
```json
{
  "project": "project_name",
  "findings": [{
    "title": "Reentrancy in withdraw",
    "description": "Details...",
    "severity": "high",
    "location": "withdraw() function",
    "file": "Vault.sol"
  }]
}
```
[See full format specification](./HOW_IT_WORKS.md#step-3-format-your-results)

**Step 4: Score your results**
```bash
python scoring/scorer.py \
  --benchmark datasets/curated-2025-08-18.json \
  --results-dir results/
```

**Step 5: View your performance**
```bash
python scoring/report_generator.py \
  --scores scores/ \
  --output my_tool_report.html
```

## Installation

### Requirements
- Python 3.8+
- OpenAI API key
- 4GB+ RAM for large codebases

### Setup
```bash
# Clone the repository
git clone https://github.com/scabench/scabench.git
cd scabench

# Install all dependencies
pip install -r requirements.txt

# Set up configuration (optional)
cp config.example.json config.json
# Edit config.json with your preferences

# Run tests to verify installation
pytest tests/
```

## Strict Matching Policy

The scorer enforces EXTREMELY STRICT matching criteria:

- ✅ **IDENTICAL LOCATION** - Must be exact same file/contract/function
- ✅ **EXACT IDENTIFIERS** - Same contract names, function names, variables  
- ✅ **IDENTICAL ROOT CAUSE** - Must be THE SAME vulnerability
- ✅ **IDENTICAL ATTACK VECTOR** - Exact same exploitation method
- ✅ **IDENTICAL IMPACT** - Exact same security consequence
- ❌ **NO MATCH** for similar patterns in different locations
- ❌ **NO MATCH** for same bug type but different functions
- ⚠️ **WHEN IN DOUBT: DO NOT MATCH**

**Only findings with confidence = 1.0 count as true positives!**

## Performance Tips

1. **Model Selection**:
   - Use `gpt-5-mini` for both baseline analysis and scoring (best accuracy)
   - Use `gpt-4o-mini` for faster processing with slightly lower accuracy
   - Use `--max-files` to limit analysis during testing

2. **Batch Processing**:
   ```bash
   # Process multiple projects
   for project in project1 project2 project3; do
     ./run_pipeline.sh --project $project --source sources/$project
   done
   ```

3. **Caching**: Results are saved to disk for reprocessing

## Output Formats

### Baseline Results
```json
{
  "project": "vulnerable_vault",
  "files_analyzed": 10,
  "total_findings": 5,
  "findings": [{
    "title": "Reentrancy vulnerability",
    "severity": "high",
    "confidence": 0.95,
    "location": "withdraw() function"
  }]
}
```

### Scoring Results  
```json
{
  "total_expected": 10,
  "true_positives": 6,
  "detection_rate": 0.6,
  "matched_findings": [{
    "confidence": 1.0,
    "justification": "Perfect match: identical vulnerability"
  }]
}
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

See individual component READMEs for detailed development guidelines.

## License

MIT License - see LICENSE file for details

## Documentation Links

### Core Documentation
- 📖 [How It Works](./HOW_IT_WORKS.md) - Complete system overview
- 🚀 [Quick Start Guide](./QUICK_START.md) - Get started quickly
- 📊 [Dataset Documentation](./datasets/README.md) - Dataset format and creation
- 🔧 [Tool Documentation](./TOOLING_README.md) - Detailed tool usage
- 🧪 [Testing Guide](./tests/) - Running and writing tests

### Support
- 🐛 [Report Issues](https://github.com/scabench/scabench/issues)
- 💬 [Discussions](https://github.com/scabench/scabench/discussions)
