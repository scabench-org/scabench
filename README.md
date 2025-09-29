# ScaBench: Smart Contract Audit Benchmark

A comprehensive framework for evaluating security analysis tools and AI agents on real-world smart contract vulnerabilities. ScaBench provides curated datasets from recent audits and official tooling for consistent evaluation.

## Features

- 🎯 **Curated Datasets**: Real-world vulnerabilities from Code4rena, Cantina, and Sherlock audits
- 🤖 **Baseline Runner**: LLM-based security analyzer with configurable models
- 📊 **Scoring Tool**: Official Nethermind AuditAgent scoring algorithm
- 📈 **Report Generator**: HTML reports with visualizations and performance metrics
- 🔄 **Composable CLI**: End-to-end examples for single or all projects

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

### 📈 **Scorer** (Nethermind AuditAgent algorithm)
Official scoring now uses Nethermind's AuditAgent algorithm. The previous `scoring/scorer_v2.py` is deprecated.

- Upstream repo: https://github.com/NethermindEth/auditagent-scoring-algo

Install the scorer (either clone and install, or install directly from Git):
```bash
pip install "git+https://github.com/NethermindEth/auditagent-scoring-algo"
# or
git clone https://github.com/NethermindEth/auditagent-scoring-algo.git
cd auditagent-scoring-algo && pip install -e .
```

Scorer data layout (you create this):
- `<DATA_ROOT>/<SCAN_SOURCE>/<project>_results.json`   # your tool’s findings (e.g., `SCAN_SOURCE=baseline`)
- `<DATA_ROOT>/source_of_truth/<project>.json`         # per-project ground truth

Prepare truth files from the curated dataset:
```bash
export DATA_ROOT="$(pwd)/scoring_data"
mkdir -p "$DATA_ROOT/source_of_truth"
python - <<'PY'
import json, os, pathlib
dataset = json.load(open('datasets/curated-2025-08-18/curated-2025-08-18.json'))
out = pathlib.Path(os.environ.get('DATA_ROOT','./scoring_data'))/ 'source_of_truth'
out.mkdir(parents=True, exist_ok=True)
for item in dataset:
    (out/f"{item['project_id']}.json").write_text(json.dumps(item, indent=2))
print(f"Wrote {len(dataset)} truth files to {out}")
PY
```

Place your findings for each project (from your analyzer or the baseline runner) as:
```bash
mkdir -p "$DATA_ROOT/baseline"
# Example: after running baseline-runner (below), move/rename to the expected name
PROJECT_ID=code4rena_kinetiq_2025_07
mv baseline_results/baseline_${PROJECT_ID}.json "$DATA_ROOT/baseline/${PROJECT_ID}_results.json"
```

Run the scorer:
```bash
export OPENAI_API_KEY=...   # required
export MODEL=o4-mini        # or another supported OpenAI model
export REPOS_TO_RUN='["code4rena_kinetiq_2025_07"]'   # list of project IDs
export DATA_ROOT="$DATA_ROOT"
export OUTPUT_ROOT="$(pwd)/scoring_output"
export SCAN_SOURCE=baseline  # or auditagent
python -m scoring_algo.cli evaluate --no-telemetry --log-level INFO

# Generate Markdown report from results
python -m scoring_algo.generate_report \
  --benchmarks "$OUTPUT_ROOT" \
  --scan-root "$DATA_ROOT/$SCAN_SOURCE" \
  --out REPORT.md
```

### 📄 **Report Generation**
- Via AuditAgent algo (preferred):
  - Markdown summary: `python -m scoring_algo.generate_report --benchmarks <OUTPUT_ROOT> --scan-root <DATA_ROOT>/<SCAN_SOURCE> --out REPORT.md`
- Legacy HTML generator (works with legacy `scorer_v2.py` JSON):
  - `python scoring/report_generator.py --scores <scores_dir> --output report.html`

## Quick Start

### Prerequisites
```bash
# Install dependencies
pip install -r requirements.txt

# Set OpenAI API key
export OPENAI_API_KEY="your-key-here"
```

### Quick Start: CLI Guides

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

# Step 5: Score the results using AuditAgent algorithm
pip install "git+https://github.com/NethermindEth/auditagent-scoring-algo"
export DATA_ROOT="$(pwd)/scoring_data" && mkdir -p "$DATA_ROOT/baseline" "$DATA_ROOT/source_of_truth"
# Create truth files from curated dataset (one per project)
python - <<'PY'
import json, os, pathlib
dataset = json.load(open('datasets/curated-2025-08-18/curated-2025-08-18.json'))
out = pathlib.Path(os.environ['DATA_ROOT'])/ 'source_of_truth'
out.mkdir(parents=True, exist_ok=True)
for item in dataset:
    (out/f"{item['project_id']}.json").write_text(json.dumps(item, indent=2))
PY
# Place/rename baseline output for this project
mv datasets/curated-2025-08-18/baseline-results/baseline_${PROJECT_ID}.json "$DATA_ROOT/baseline/${PROJECT_ID}_results.json"
# Run scoring
export OPENAI_API_KEY=...; export MODEL=o4-mini; export REPOS_TO_RUN='["'"$PROJECT_ID"'"]'; export OUTPUT_ROOT="$(pwd)/scoring_output"; export SCAN_SOURCE=baseline
python -m scoring_algo.cli evaluate --no-telemetry --log-level INFO

# Step 6: Generate Markdown report from evaluated results
python -m scoring_algo.generate_report \
  --benchmarks "$OUTPUT_ROOT" \
  --scan-root "$DATA_ROOT/$SCAN_SOURCE" \
  --out REPORT.md

# Step 7: View the report
open REPORT.md  # macOS
# xdg-open REPORT.md  # Linux
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

# Step 4: Score ALL prepared results using AuditAgent algorithm
pip install "git+https://github.com/NethermindEth/auditagent-scoring-algo"
export DATA_ROOT="$(pwd)/scoring_data" && mkdir -p "$DATA_ROOT/baseline" "$DATA_ROOT/source_of_truth" "$OUTPUT_ROOT"
# (Optionally) split truth for all projects
python - <<'PY'
import json, os, pathlib
dataset = json.load(open('datasets/curated-2025-08-18/curated-2025-08-18.json'))
root = pathlib.Path(os.environ['DATA_ROOT'])
truth = root/ 'source_of_truth'; truth.mkdir(parents=True, exist_ok=True)
for item in dataset:
    (truth/f"{item['project_id']}.json").write_text(json.dumps(item, indent=2))
print(f"Wrote {len(dataset)} truth files to {truth}")
PY
# Move/rename all baseline outputs into $DATA_ROOT/baseline as <project>_results.json
for f in datasets/curated-2025-08-18/baseline-results/baseline_*.json; do 
  p=$(basename "$f" .json | sed 's/^baseline_//'); 
  mv "$f" "$DATA_ROOT/baseline/${p}_results.json"; 
done
# List of projects to score (JSON array of project IDs)
export REPOS_TO_RUN=$(jq -r '.[].project_id' datasets/curated-2025-08-18/curated-2025-08-18.json | jq -R -s -c 'split("\n")[:-1]')
export OPENAI_API_KEY=...; export MODEL=o4-mini; export OUTPUT_ROOT="$(pwd)/scoring_output"; export SCAN_SOURCE=baseline
python -m scoring_algo.cli evaluate --no-telemetry --log-level INFO

# Step 5: Generate a Markdown summary report
python -m scoring_algo.generate_report \
  --benchmarks "$OUTPUT_ROOT" \
  --scan-root "$DATA_ROOT/$SCAN_SOURCE" \
  --out REPORT.md

# Step 6: View the report
open REPORT.md  # macOS (opens in default editor)
# xdg-open REPORT.md  # Linux
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
# Score with AuditAgent algorithm
pip install "git+https://github.com/NethermindEth/auditagent-scoring-algo"
export DATA_ROOT="$(pwd)/scoring_data" && mkdir -p "$DATA_ROOT/baseline" "$DATA_ROOT/source_of_truth"
mv baseline_results/baseline_${PROJECT_ID}.json "$DATA_ROOT/baseline/${PROJECT_ID}_results.json"
python - <<'PY'
import json, os, pathlib
dataset = json.load(open('datasets/curated-2025-08-18/curated-2025-08-18.json'))
proj = os.environ['PROJECT_ID']
item = next((x for x in dataset if x.get('project_id') == proj), None)
out = pathlib.Path(os.environ['DATA_ROOT'])/'source_of_truth'/f"{proj}.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(item, indent=2))
print('Wrote truth to', out)
PY
export OPENAI_API_KEY=...; export MODEL=o4-mini; export REPOS_TO_RUN='["'"$PROJECT_ID"'"]'; export OUTPUT_ROOT="$(pwd)/scoring_output"; export SCAN_SOURCE=baseline
python -m scoring_algo.cli evaluate --no-telemetry --log-level INFO
python -m scoring_algo.generate_report --benchmarks "$OUTPUT_ROOT" --scan-root "$DATA_ROOT/$SCAN_SOURCE" --out REPORT.md
```

## Evaluate YOUR Tool

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

**Step 4: Score your results (AuditAgent algorithm)**
Two options:

Run the scorer after placing files per layout:
```bash
# Prepare data layout manually
# <DATA_ROOT>/baseline/<project>_results.json
# <DATA_ROOT>/source_of_truth/<project>.json  # per-project truth JSON

export OPENAI_API_KEY=...
export MODEL=o4-mini
export REPOS_TO_RUN='["<project>"]'
export DATA_ROOT="/path/to/DATA_ROOT"
export OUTPUT_ROOT="/path/to/benchmarks"
export SCAN_SOURCE=baseline
python -m scoring_algo.cli evaluate --no-telemetry --log-level INFO
```

**Step 5: View your performance**
```bash
python -m scoring_algo.generate_report \
  --benchmarks "$OUTPUT_ROOT" \
  --scan-root "$DATA_ROOT/$SCAN_SOURCE" \
  --out REPORT.md
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

## Matching Policy (AuditAgent algorithm)

The scorer follows AuditAgent's matching rules:

- ✅ **One-to-one mapping**: At most one junior finding per truth finding
- ✅ **Exact matches**: Count as true positives; short‑circuit further search for that truth
- ➖ **Partial matches**: Tracked separately; de‑duplicated by junior index; do not count as exact TPs
- ❌ **Non‑matches**: Representative non‑match recorded for transparency
- 🔁 **Batch + majority**: For each truth, batches of findings are evaluated with multiple LLM iterations; majority vote selects the outcome
- 🧹 **False positives**: Remaining junior findings (excluding Info/Best Practices) are appended as FPs after matching

## Performance Tips

1. **Model selection**:
   - Scoring default in this repo: `o4-mini` (set `MODEL` env var)
   - Tune `ITERATIONS` (e.g., 3) and `BATCH_SIZE` (e.g., 10) via env or wrapper args
   - Baseline analysis remains independent; pick your preferred analysis model

2. **Batch processing**:
   ```bash
   # Process multiple projects using the baseline runner
   for project in project1 project2 project3; do
     python baseline-runner/baseline_runner.py \
       --project "$project" \
       --source "sources/$project" \
       --output baseline_results \
       --model gpt-5-mini
   done
   ```

3. **Caching**: Scorer writes per‑project evaluated results and a Markdown report; re‑runs reuse prepared data

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

### Scoring Results (AuditAgent algorithm)
Per‑project evaluated results are written to `<OUTPUT_ROOT>/<project>_results.json` as an array of evaluated findings. Example item:
```json
{
  "is_match": true,
  "is_partial_match": false,
  "is_fp": false,
  "explanation": "Exact match: same function and root cause",
  "severity_from_junior_auditor": "High",
  "severity_from_truth": "High",
  "index_of_finding_from_junior_auditor": 3,
  "finding_description_from_junior_auditor": "Unchecked external call in withdraw() allows reentrancy"
}
```

## License

MIT License - see LICENSE file for details
