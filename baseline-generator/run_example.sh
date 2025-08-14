#!/bin/bash

# Example script to run baseline analysis on a dataset

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY environment variable is not set"
    echo "Please set it with: export OPENAI_API_KEY=your_api_key_here"
    exit 1
fi

# Check if dataset file is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <dataset.json> [project_filter] [--no-resume|--clear-session]"
    echo ""
    echo "Examples:"
    echo "  $0 dataset.json                    # Run all projects (auto-resume)"
    echo "  $0 dataset.json virtuals           # Run specific project"
    echo "  $0 dataset.json \"\" --no-resume     # Run all, don't resume"
    echo "  $0 dataset.json \"\" --clear-session # Clear session and start fresh"
    exit 1
fi

DATASET_FILE=$1
PROJECT_FILTER=${2:-""}

# Create output directory with timestamp
OUTPUT_DIR="baseline_results_$(date +%Y%m%d_%H%M%S)"

echo "Running baseline analysis..."
echo "Dataset: $DATASET_FILE"
echo "Output directory: $OUTPUT_DIR"

# Check for resume flag
RESUME_FLAG=""
if [ "$3" = "--no-resume" ]; then
    RESUME_FLAG="--no-resume"
    echo "Starting fresh (no resume)"
elif [ "$3" = "--clear-session" ]; then
    RESUME_FLAG="--clear-session"
    echo "Clearing previous session"
else
    echo "Will resume from previous session if available"
fi

if [ -n "$PROJECT_FILTER" ]; then
    echo "Project filter: $PROJECT_FILTER"
    python baseline_runner.py "$DATASET_FILE" \
        --output-dir "$OUTPUT_DIR" \
        --project "$PROJECT_FILTER" \
        --max-files 20 \
        --cache-dir ~/.baseline_cache \
        $RESUME_FLAG \
        --verbose
else
    python baseline_runner.py "$DATASET_FILE" \
        --output-dir "$OUTPUT_DIR" \
        --max-files 20 \
        --cache-dir ~/.baseline_cache \
        $RESUME_FLAG
fi

echo ""
echo "Analysis complete. Results saved to: $OUTPUT_DIR"
echo ""
echo "Summary:"
if [ -f "$OUTPUT_DIR/baseline_summary.json" ]; then
    python -c "
import json
with open('$OUTPUT_DIR/baseline_summary.json', 'r') as f:
    data = json.load(f)
    successful = sum(1 for r in data.values() if r.get('status') == 'success')
    failed = sum(1 for r in data.values() if r.get('status') == 'failed')
    total_findings = sum(r.get('findings_count', 0) for r in data.values() if r.get('status') == 'success')
    print(f'  Projects analyzed: {successful}')
    print(f'  Projects failed: {failed}')
    if successful > 0:
        print(f'  Total findings: {total_findings}')
        print(f'  Average findings per project: {total_findings/successful:.1f}')
"
fi