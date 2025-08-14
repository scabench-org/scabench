#!/bin/bash

# Batch test script for baseline generator with evaluation

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY environment variable is not set"
    echo "Please set it with: export OPENAI_API_KEY=your_api_key_here"
    exit 1
fi

# Configuration
DATASET="../datasets/scabench_2025-02_to_2025-08.json"
OUTPUT_DIR="batch_test_output"
MAX_FILES=10  # Analyze up to 10 files per project

# Projects to test (add more as needed)
PROJECTS=(
    "BitVault"
    "Nudge.xyz"
    "Forte: Float128 Solidity Library"
)

echo "=========================================="
echo "BASELINE BATCH TEST"
echo "=========================================="
echo "Dataset: $DATASET"
echo "Output: $OUTPUT_DIR"
echo "Max files per project: $MAX_FILES"
echo "Projects to test: ${#PROJECTS[@]}"
echo ""

# Clear previous session
echo "Clearing previous session..."
rm -rf "$OUTPUT_DIR/.session"

# Run baseline for each project
for project in "${PROJECTS[@]}"; do
    echo ""
    echo "------------------------------------------"
    echo "Analyzing: $project"
    echo "------------------------------------------"
    
    python baseline_runner.py "$DATASET" \
        --output-dir "$OUTPUT_DIR" \
        --project "$project" \
        --max-files "$MAX_FILES" \
        --cache-dir ~/.baseline_cache \
        2>&1 | tail -5
    
    if [ $? -eq 0 ]; then
        echo "✓ Completed: $project"
    else
        echo "✗ Failed: $project"
    fi
done

echo ""
echo "=========================================="
echo "RUNNING EVALUATION"
echo "=========================================="
echo ""

# Run evaluation
python evaluate_baseline.py "$OUTPUT_DIR" "$DATASET"

echo ""
echo "=========================================="
echo "BATCH TEST COMPLETE"
echo "=========================================="
echo "Results saved to: $OUTPUT_DIR"
echo "Evaluation saved to: $OUTPUT_DIR/evaluation"