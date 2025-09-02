# ScaBench: Smart Contract Audit Benchmark

A comprehensive framework for evaluating security analysis tools and AI agents on real-world smart contract vulnerabilities. ScaBench provides curated datasets from recent audits and official tooling for consistent evaluation.

## 📚 Dataset Documentation

- **[Dataset Format & Statistics](./datasets/README.md)** - Complete dataset information

## Features

- 🎯 **Curated Datasets**: Real-world vulnerabilities from Code4rena, Cantina, and Sherlock audits
- 🤖 **Baseline Runner**: LLM-based security analyzer with configurable models
- 📊 **Scoring Tool**: Evaluates findings with LLM-based matching (confidence = 1.0 only)
- 📈 **Report Generator**: HTML reports with visualizations and performance metrics
- 🔄 **Pipeline Automation**: Complete workflow with single-command execution

## Available Curated Datasets

> **Note**: New datasets are added regularly to prevent models from being trained on known results and to maintain benchmark integrity.

### Current Dataset: curated-2025-08-18
**Location**: `datasets/curated-2025-08-18/curated-2025-08-18.json`

The most current dataset contains contest scope repositories with expected vulnerabilities from audit competitions:
- **31 projects** from Code4rena, Cantina, and Sherlock platforms  
- **555 total vulnerabilities** (114 high/critical severity)
- **Time range**: 2024-08 to 2025-08
- **Data format**: JSON with project metadata including:
  - `project_id`: Unique identifier for each project
  - `codebases`: Repository URLs, commit hashes, and download links
  - `vulnerabilities`: Array of findings with severity, title, and detailed descriptions

### Baseline Results
**Location**: `datasets/curated-2025-08-18/baseline-results/`

Pre-computed baseline results from analyzing each individual file with GPT-5:
- **Approach**: Single-file analysis using GPT-5 to identify vulnerabilities
- **Coverage**: One baseline file per project (e.g., `baseline_cantina_minimal-delegation_2025_04.json`)
- **Data format**: JSON containing:
  - `project`: Project identifier
  - `files_analyzed`: Number of files processed
  - `total_findings`: Count of vulnerabilities found
  - `findings`: Array of identified issues with:
    - `title`: Brief vulnerability description
    - `description`: Detailed explanation
    - `severity`: Risk level (high/medium/low)
    - `confidence`: Model's confidence score
    - `location`: Specific code location
    - `file`: Source file name

## What Each Component Does

### 📊 **Official Datasets** (`datasets/`)
Pre-curated benchmark datasets with real vulnerabilities from audits.
- **Current**: `curated-2025-08-18.json` (31 projects, 555 vulnerabilities)
- Format: JSON with project metadata, repo URLs, commits, and vulnerability details

### 🔧 **Dataset Generator** (`dataset-generator/`)
Create NEW datasets by scraping and curating audit data.

**Step 1: Scrape audit platforms**
```bash
cd dataset-generator
python scraper.py --platforms code4rena cantina sherlock --months 3
```

**Step 2: Curate the dataset**
```bash
# Filter projects based on quality criteria
python curate_dataset.py \
  --input raw_dataset.json \
  --output curated_dataset.json \
  --min-vulnerabilities 5 \
  --min-high-critical 1

# This filters out projects that:
# - Have fewer than 5 vulnerabilities
# - Have no high/critical severity findings
# - Have inaccessible GitHub repositories
# - Have invalid or missing data
```

The curation step ensures high-quality benchmark data by removing low-value or inaccessible projects.

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

### 📈 **Scorer** (`scoring/scorer_v2.py`)
Evaluates ANY tool's findings against the benchmark using LLM matching with one-by-one comparison for better consistency.

**Important: Model Requirements**
- The scorer uses one-by-one matching - processes each expected finding sequentially
- More deterministic than batch matching with fixed seed and zero temperature
- **Recommended**: `gpt-4o` (default, best accuracy)
- **Alternative**: `gpt-4o-mini` (faster, cheaper, good for testing)

#### Scoring a Single Project

**IMPORTANT**: When scoring a single project, you must specify the exact project ID from the benchmark dataset using the `--project` flag. Project IDs often contain hyphens (e.g., `code4rena_iq-ai_2025_03`) while baseline result filenames may have underscores.

```bash
# Example: Score results for a single project
python scoring/scorer_v2.py \
  --benchmark datasets/curated-2025-08-18/curated-2025-08-18.json \
  --results-dir datasets/curated-2025-08-18/baseline-results/ \
  --project code4rena_iq-ai_2025_03 \
  --model gpt-4o \
  --confidence-threshold 0.75

# With verbose output to see matching details
python scoring/scorer_v2.py \
  --benchmark datasets/curated-2025-08-18/curated-2025-08-18.json \
  --results-dir datasets/curated-2025-08-18/baseline-results/ \
  --project code4rena_iq-ai_2025_03 \
  --verbose
```

Note: The `--project` parameter must match the exact `project_id` field from the benchmark dataset JSON. Check the dataset file if unsure about the correct project ID.

#### Scoring an Entire Baseline Run (All Projects)

To score all baseline results at once:

```bash
# Score all baseline results in a directory
python scoring/scorer_v2.py \
  --benchmark datasets/curated-2025-08-18/curated-2025-08-18.json \
  --results-dir datasets/curated-2025-08-18/baseline-results/ \
  --output scores/ \
  --model gpt-4o \
  --confidence-threshold 0.75

# This will:
# 1. Process all *.json files in the results directory
# 2. Automatically extract and match project IDs
# 3. Generate individual score files for each project
# 4. Save results to the scores/ directory

# With debug output
python scoring/scorer_v2.py \
  --benchmark datasets/curated-2025-08-18/curated-2025-08-18.json \
  --results-dir datasets/curated-2025-08-18/baseline-results/ \
  --output scores/ \
  --debug
```

#### Available Options
- `--confidence-threshold`: Set matching confidence threshold (default: 0.75)
- `--verbose`: Show detailed matching progress for each finding
- `--debug`: Enable debug output for troubleshooting

After scoring, generate a comprehensive report:
```bash
python scoring/report_generator.py \
  --scores scores/ \
  --output baseline_report.html \
  --tool-name "Baseline" \
  --model gpt-5-mini
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

The `run_all.sh` script provides a complete end-to-end pipeline that:

1. **Downloads source code** - Clones all project repositories at exact audit commits
2. **Runs baseline analysis** - Analyzes each project with LLM-based security scanner
3. **Scores results** - Evaluates findings against known vulnerabilities using strict matching
4. **Generates reports** - Creates comprehensive HTML report with metrics and visualizations

#### Basic Usage
```bash
# Run everything with defaults (all projects in dataset, gpt-5-mini model)
./run_all.sh

# Use different model (e.g., gpt-4o-mini for faster/cheaper runs)
./run_all.sh --model gpt-4o-mini

# Use a different dataset
./run_all.sh --dataset datasets/my_custom_dataset.json

# Combine options
./run_all.sh --model gpt-4o-mini --output-dir test_run
```

#### All Options
```bash
./run_all.sh [OPTIONS]

Options:
  --dataset FILE       Dataset to use (default: datasets/curated-2025-08-18.json)
  --model MODEL        Model for analysis (default: gpt-5-mini)
                       Options: gpt-5-mini, gpt-4o-mini, gpt-4o
  --output-dir DIR     Output directory (default: all_results_TIMESTAMP)
  --skip-checkout      Skip source checkout (use existing sources)
  --skip-baseline      Skip baseline analysis (use existing results)
  --skip-scoring       Skip scoring and report generation
  --help               Show help
```

#### What It Does (Step by Step)

**Step 1: Source Checkout**
- Downloads all projects from the dataset (from their GitHub repositories)
- Checks out exact commits from audit time
- Preserves original project structure
- Creates: `OUTPUT_DIR/sources/PROJECT_ID/`

**Step 2: Baseline Analysis**
- Runs LLM-based security analysis on each project
- Configurable file limits for testing
- Uses specified model (default: gpt-5-mini)
- Creates: `OUTPUT_DIR/baseline_results/baseline_PROJECT_ID.json`

**Step 3: Scoring**
- Compares findings against known vulnerabilities in the dataset
- Uses STRICT matching (confidence = 1.0 only)
- Batch processes all projects
- Creates: `OUTPUT_DIR/scoring_results/score_PROJECT_ID.json`

**Step 4: Report Generation**
- Aggregates all scoring results
- Generates HTML report with charts and metrics
- Calculates overall detection rates and F1 scores
- Creates: `OUTPUT_DIR/reports/full_report.html`

**Step 5: Summary Statistics**
- Computes aggregate metrics across all projects
- Saves summary JSON with key statistics
- Creates: `OUTPUT_DIR/summary.json`

#### Performance Notes

- **Full run (all files)**: 4-6 hours for default dataset (31 projects)
- **Fast test (--model gpt-4o-mini)**: 30-45 minutes
- **Model selection**:
  - `gpt-5-mini`: Best accuracy (default)
  - `gpt-4o-mini`: Faster, cheaper, good for testing

**Note**: The default dataset (`curated-2025-08-18.json`) contains 31 projects with 555 total vulnerabilities. Custom datasets may have different counts.

### Option 2: Process Single Project
```bash
# For a specific project
./run_pipeline.sh --project vulnerable_vault --source sources/vulnerable_vault
```

### Option 3: Complete Command-Line Guides

#### Complete Guide: Analyze and Score a Single Project

```bash
# Step 1: Set up environment
export OPENAI_API_KEY="your-key-here"

# Step 2: Find your project ID in the dataset
PROJECT_ID="code4rena_iq-ai_2025_03"  # Example - check dataset for exact ID

# Step 3: Download the source code
python dataset-generator/checkout_sources.py \
  --dataset datasets/curated-2025-08-18.json \
  --project $PROJECT_ID \
  --output sources/

# Step 4: Run baseline analysis
python baseline-runner/baseline_runner.py \
  --project $PROJECT_ID \
  --source sources/${PROJECT_ID//-/_} \
  --output datasets/curated-2025-08-18/baseline-results/ \
  --model gpt-5-mini

# Step 5: Score the results (IMPORTANT: use exact project ID with hyphens)
python scoring/scorer_v2.py \
  --benchmark datasets/curated-2025-08-18/curated-2025-08-18.json \
  --results-dir datasets/curated-2025-08-18/baseline-results/ \
  --project $PROJECT_ID \
  --output scores/ \
  --model gpt-4o

# Step 6: Generate HTML report
python scoring/report_generator.py \
  --scores scores/ \
  --output single_project_report.html \
  --tool-name "Baseline" \
  --model gpt-5-mini

# Step 7: View the report
open single_project_report.html  # macOS
# xdg-open single_project_report.html  # Linux
```

#### Complete Guide: Analyze and Score ALL Projects

```bash
# Step 1: Set up environment
export OPENAI_API_KEY="your-key-here"

# Step 2: Download ALL project sources (this may take a while)
python dataset-generator/checkout_sources.py \
  --dataset datasets/curated-2025-08-18.json \
  --output sources/

# Step 3: Run baseline on ALL projects (this will take hours)
for dir in sources/*/; do
  project=$(basename "$dir")
  echo "Analyzing $project..."
  python baseline-runner/baseline_runner.py \
    --project "$project" \
    --source "$dir" \
    --output datasets/curated-2025-08-18/baseline-results/ \
    --model gpt-5-mini \
done

# Step 4: Score ALL baseline results
python scoring/scorer_v2.py \
  --benchmark datasets/curated-2025-08-18/curated-2025-08-18.json \
  --results-dir datasets/curated-2025-08-18/baseline-results/ \
  --output scores/ \
  --model gpt-4o

# Step 5: Generate comprehensive report
python scoring/report_generator.py \
  --scores scores/ \
  --output full_baseline_report.html \
  --tool-name "Baseline Analysis" \
  --model gpt-5-mini

# Step 6: View the report
open full_baseline_report.html  # macOS
# xdg-open full_baseline_report.html  # Linux
```

#### Quick Test Run (Small Sample)

```bash
# Test with just one small project for quick validation
export OPENAI_API_KEY="your-key-here"

# Pick a small project
PROJECT_ID="code4rena_coded-estate-invitational_2024_12"

# Run complete pipeline for single project
python dataset-generator/checkout_sources.py --project $PROJECT_ID --output sources/
python baseline-runner/baseline_runner.py \
  --project $PROJECT_ID \
  --source sources/${PROJECT_ID//-/_} \
  --model gpt-5-mini
python scoring/scorer_v2.py \
  --benchmark datasets/curated-2025-08-18/curated-2025-08-18.json \
  --results-dir datasets/curated-2025-08-18/baseline-results/ \
  --project $PROJECT_ID \
  --model gpt-4o
python scoring/report_generator.py \
  --scores scores/ \
  --output test_report.html \
  --model gpt-5-mini
open test_report.html
```

### Option 4: Step-by-Step Manual Process

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
python scoring/scorer_v2.py \
  --benchmark datasets/curated-2025-08-18/curated-2025-08-18.json \
  --results-dir datasets/curated-2025-08-18/baseline-results/ \
  --project vulnerable_vault

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
[See format specification below](#output-formats)

**Step 4: Score your results**
```bash
python scoring/scorer_v2.py \
  --benchmark datasets/curated-2025-08-18/curated-2025-08-18.json \
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
   - **For Scoring**: Use `gpt-5-mini` (recommended) - needs long context for batch matching
   - **For Baseline Analysis**: Use `gpt-5-mini` for best accuracy
   - **Important**: The scorer processes ALL findings in a single LLM call, so a model with sufficient context window is critical
   - Use `gpt-4o` if you encounter context length errors with very large projects
   - Use `--patterns` to specify which files to analyze

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

## License

MIT License - see LICENSE file for details
