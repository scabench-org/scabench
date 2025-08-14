# Baseline Generator

A baseline security analysis tool that uses LLMs to analyze source code repositories for vulnerabilities. This serves as a baseline for evaluating more sophisticated audit agents. The tool includes comprehensive evaluation capabilities to compare findings against expected vulnerabilities from real audits.

## Features

- **Automatic Repository Download**: Downloads and caches repositories from GitHub and other sources
- **Multi-Language Support**: Analyzes Solidity, Rust, Go, JavaScript, Python, Cairo, Move, and Vyper code
- **LLM-Based Analysis**: Uses trivial LLM prompting to identify security vulnerabilities
- **Deduplication**: Automatically deduplicates similar findings
- **Session Management**: Resume interrupted runs automatically
- **Evaluation System**: Compare findings against expected vulnerabilities
- **Structured Output**: Generates JSON output with detailed metrics

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```bash
# Set API key
export OPENAI_API_KEY=your_api_key_here

# Run baseline analysis
python baseline_runner.py path/to/dataset.json --output-dir results

# Evaluate the results
python evaluate_baseline.py results path/to/dataset.json
```

## Usage

### Basic Usage

```bash
export OPENAI_API_KEY=your_api_key_here
python baseline_runner.py path/to/dataset.json
```

### Command Line Options

```bash
python baseline_runner.py dataset.json \
  --output-dir results \
  --model gpt-5-mini \
  --cache-dir ~/.repo_cache \
  --max-files 50 \
  --project "project_name" \
  --no-resume \
  --verbose
```

#### Options:
- `dataset`: Path to the dataset JSON file (required)
- `--output-dir`: Directory to save results (default: baseline_results)
- `--model`: OpenAI model to use (default: gpt-5)
- `--cache-dir`: Directory to cache downloaded repositories
- `--max-files`: Maximum number of files to analyze per project
- `--project`: Filter to run on specific project (partial name match)
- `--no-resume`: Do not resume from previous session
- `--clear-session`: Clear previous session and start fresh
- `--session-dir`: Directory to store session state (default: output_dir/.session)
- `--verbose`: Enable verbose logging

## Output Format

Each project analysis generates a JSON file with the following structure:

```json
{
  "project_id": "project_identifier",
  "project_name": "Project Name",
  "platform": "code4rena",
  "analysis_date": "2024-01-01T00:00:00",
  "model": "gpt-5-mini",
  "findings_count": 10,
  "findings": [
    {
      "file_path": "contracts/Token.sol",
      "severity": "high",
      "title": "Reentrancy vulnerability",
      "description": "The withdraw function is vulnerable to reentrancy...",
      "line_start": 45,
      "line_end": 52,
      "confidence": 0.85
    }
  ],
  "expected_vulnerabilities": [...]
}
```

## Session Management

The baseline generator includes automatic session management for handling long-running processes. Sessions are automatically saved and can be resumed if interrupted.

### Features:
- **Automatic Resume**: By default, the tool will resume from where it left off if interrupted
- **Progress Tracking**: Shows completion percentage and remaining projects
- **Project-level Checkpoints**: Saves progress after each project completion
- **Crash Recovery**: Can recover from unexpected interruptions

### Usage:

```bash
# Start a new analysis (will auto-resume if previous session exists)
python baseline_runner.py dataset.json

# Force start fresh (ignore previous session)
python baseline_runner.py dataset.json --no-resume

# Clear session and start fresh
python baseline_runner.py dataset.json --clear-session

# Use custom session directory
python baseline_runner.py dataset.json --session-dir /path/to/session
```

When resuming, the tool will:
1. Display a summary of the previous session
2. Skip already processed projects
3. Continue from the last incomplete project
4. Maintain all previous results

Session state is stored in `{output_dir}/.session/session_state.json` by default.

## How It Works

1. **Repository Download**: The tool downloads each repository specified in the dataset, using the provided commit hash if available.

2. **Source File Discovery**: It automatically detects the programming language and finds all relevant source files, excluding tests and dependencies.

3. **LLM Analysis**: Each source file is analyzed by the LLM for security vulnerabilities. The model is prompted to only report issues it's confident about (confidence > 0.7).

4. **Deduplication**: Similar findings are automatically deduplicated based on file path, title, and severity.

5. **Output Generation**: Results are saved in a structured JSON format that includes both the findings and the expected vulnerabilities from the dataset for easy comparison.

## File Types Analyzed

- **Solidity**: `.sol`
- **Rust**: `.rs`
- **Go**: `.go`
- **JavaScript/TypeScript**: `.js`, `.ts`, `.jsx`, `.tsx`
- **Python**: `.py`
- **Cairo**: `.cairo`
- **Move**: `.move`
- **Vyper**: `.vy`

## Excluded Paths

The following paths are automatically excluded from analysis:
- Test files and directories
- Mock files
- Dependencies (node_modules, vendor, etc.)
- Build artifacts (build/, dist/, target/, out/)
- Version control (.git)
- Library directories (lib/, libs/)

## Rate Limiting

The tool includes built-in rate limiting to avoid overwhelming the OpenAI API:
- Maximum 5 parallel API calls
- 200ms delay between file submissions

## Caching

Downloaded repositories are cached to avoid redundant downloads. The cache key is based on the repository URL and commit hash.

## Complete Example

```bash
# Set API key
export OPENAI_API_KEY=sk-...

# 1. Run baseline on a specific project
python baseline_runner.py ../datasets/scabench_2025-02_to_2025-08.json \
  --project "BitVault" \
  --output-dir baseline_results \
  --max-files 10 \
  --cache-dir ~/.baseline_cache

# 2. Check the raw results
cat baseline_results/code4rena_bitvault_2025_05_baseline.json | jq '.findings_count'

# 3. Evaluate against expected vulnerabilities
python evaluate_baseline.py baseline_results ../datasets/scabench_2025-02_to_2025-08.json

# 4. Check evaluation details
cat baseline_results/evaluation/code4rena_bitvault_2025_05_evaluation.json | jq '.summary'

# 5. View overall metrics
cat baseline_results/evaluation/evaluation_summary.json | jq '.overall_metrics'
```

### Example Output

```json
{
  "total_found": 3,
  "total_missed": 5,
  "total_false_positives": 2,
  "overall_recall": "37.5%"
}
```

## Output Files

### Baseline Results
- Individual project results: `{output_dir}/{project_id}_baseline.json`
- Summary of all runs: `{output_dir}/baseline_summary.json`
- Session state: `{output_dir}/.session/session_state.json`

### Evaluation Results (after running evaluation)
- Evaluation summary: `{output_dir}/evaluation/evaluation_summary.json`
- Per-project evaluation: `{output_dir}/evaluation/{project_id}_evaluation.json`

## Evaluating Results

After running the baseline generator, you can evaluate how well it performed against expected vulnerabilities:

### Running Evaluation

```bash
python evaluate_baseline.py <baseline_output_dir> <dataset.json>

# Example
python evaluate_baseline.py baseline_results ../datasets/scabench_2025-02_to_2025-08.json
```

### Understanding Evaluation Metrics

The evaluation produces three key metrics for each project:

1. **Found**: Issues that match expected vulnerabilities from the dataset
2. **Missed**: Expected vulnerabilities that were not detected
3. **False Positives**: Detected issues that don't match any expected vulnerability

### Evaluation Output

```
BASELINE EVALUATION SUMMARY
================================================================================
Projects Evaluated: 3
Overall Recall: 35.2%

Total Found: 12
Total Missed: 22
Total False Positives: 8

By Severity:
  HIGH: 3/5 (60.0%)
  MEDIUM: 7/20 (35.0%)
  LOW: 2/9 (22.2%)
```

## Investigating Results

### Detailed Evaluation Files

Check individual evaluation files to understand why issues matched or were missed:

```bash
# View evaluation for a specific project
cat baseline_results/evaluation/project_id_evaluation.json
```

Each evaluation file contains:
- **found_issues**: Matched vulnerabilities with similarity scores
- **missed_issues**: Expected vulnerabilities not detected
- **false_positives**: Baseline findings with no match

### Debugging Matches

The evaluation tool uses text similarity to match findings. In the evaluation files, you'll see:
- `similarity_score`: How closely the baseline finding matched the expected (0.0-1.0)
- Matches require minimum 0.25 similarity and compatible severity levels

## Batch Testing

For testing multiple projects at once, use the batch test script:

```bash
# Edit run_batch_test.sh to configure projects
./run_batch_test.sh
```

This will:
1. Run baseline analysis on multiple projects
2. Automatically evaluate results
3. Generate comprehensive reports

## Advanced Usage

### Adjusting Analysis Depth

```bash
# Analyze more files for better coverage
python baseline_runner.py dataset.json --max-files 50

# Analyze fewer files for faster results
python baseline_runner.py dataset.json --max-files 5
```

### Custom Session Management

```bash
# Force fresh start (ignore previous session)
python baseline_runner.py dataset.json --no-resume

# Clear session and start over
python baseline_runner.py dataset.json --clear-session

# Use custom session directory
python baseline_runner.py dataset.json --session-dir /custom/path
```

### Filtering Projects

```bash
# Analyze specific project (partial name match)
python baseline_runner.py dataset.json --project "Uniswap"

# Multiple specific projects
for project in "BitVault" "Nudge" "Silo"; do
    python baseline_runner.py dataset.json --project "$project"
done
```

## Performance Tips

1. **Use Repository Caching**: Speeds up repeated runs
   ```bash
   --cache-dir ~/.baseline_cache
   ```

2. **Parallel Processing**: The tool analyzes files in parallel (max 5 concurrent)

3. **Rate Limiting**: Built-in 200ms delay between API calls to avoid rate limits

4. **Session Resume**: Interrupted runs can be resumed automatically

## Notes

- Large files (>100KB) are automatically skipped to avoid token limits
- The tool focuses on security vulnerabilities, not code quality issues
- Only high-confidence findings (>0.7) are included in the results
- Informational severity issues are ignored in evaluation