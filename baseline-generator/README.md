# Baseline Generator

A baseline security analysis tool that uses LLMs to analyze source code repositories for vulnerabilities. This serves as a baseline for evaluating more sophisticated audit agents.

## Features

- **Automatic Repository Download**: Downloads and caches repositories from GitHub and other sources
- **Multi-Language Support**: Analyzes Solidity, Rust, Go, JavaScript, Python, Cairo, Move, and Vyper code
- **LLM-Based Analysis**: Uses OpenAI models (GPT-4o by default) to identify security vulnerabilities
- **Deduplication**: Automatically deduplicates similar findings
- **Structured Output**: Generates JSON output suitable for comparison with expected findings

## Installation

```bash
pip install -r requirements.txt
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
  --model gpt-4o \
  --cache-dir ~/.repo_cache \
  --max-files 50 \
  --project "project_name" \
  --no-resume \
  --verbose
```

#### Options:
- `dataset`: Path to the dataset JSON file (required)
- `--output-dir`: Directory to save results (default: baseline_results)
- `--model`: OpenAI model to use (default: gpt-4o)
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
  "model": "gpt-4o",
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

## Example

```bash
# Set API key
export OPENAI_API_KEY=sk-...

# Run on a specific project
python baseline_runner.py ../dataset-generator/datasets/scabench_2025-05_to_2025-08.json \
  --project "virtuals-protocol" \
  --output-dir baseline_results \
  --max-files 20

# Run on all projects with caching
python baseline_runner.py ../dataset-generator/datasets/scabench_2025-05_to_2025-08.json \
  --cache-dir ~/.baseline_cache \
  --output-dir baseline_results
```

## Output Files

- Individual project results: `{output_dir}/{project_id}_baseline.json`
- Summary of all runs: `{output_dir}/baseline_summary.json`

## Notes

- Large files (>100KB) are automatically skipped to avoid token limits
- The tool focuses on security vulnerabilities, not code quality issues
- Only high-confidence findings (>0.7) are included in the results