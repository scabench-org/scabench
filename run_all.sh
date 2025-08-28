#!/bin/bash
#
# ScaBench Run All - Process ALL projects from the dataset
# This script downloads sources, runs baseline analysis, scores, and generates reports for ALL projects
#
# Usage:
#   ./run_all.sh [OPTIONS]
#
# Options:
#   --dataset FILE       Dataset to use (default: datasets/curated-2025-08-18.json)
#   --max-files N        Max files per project (default: analyze all)
#   --skip-checkout      Skip source checkout (use existing sources)
#   --skip-baseline      Skip baseline analysis (use existing results)
#   --skip-scoring       Skip scoring
#   --help               Show help
#

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Default values
DATASET="datasets/curated-2025-08-18.json"
MAX_FILES=""
SKIP_CHECKOUT=false
SKIP_BASELINE=false
SKIP_SCORING=false
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="all_results_${TIMESTAMP}"

# Function to print colored output
print_color() {
    color=$1
    shift
    echo -e "${color}$@${NC}"
}

# Function to print headers
print_header() {
    echo ""
    echo "=================================================="
    print_color $CYAN "$1"
    echo "=================================================="
    echo ""
}

# Show help
show_help() {
    cat << EOF
ScaBench Run All - Process ALL projects from the dataset

Usage:
  $0 [OPTIONS]

Options:
  --dataset FILE       Dataset to use (default: datasets/curated-2025-08-18.json)
  --max-files N        Max files per project (default: analyze all)  
  --skip-checkout      Skip source checkout (use existing sources)
  --skip-baseline      Skip baseline analysis (use existing results)
  --skip-scoring       Skip scoring
  --output-dir DIR     Output directory (default: all_results_TIMESTAMP)
  --help               Show this help

Examples:
  # Run everything for all projects
  $0

  # Limit to 20 files per project for faster testing
  $0 --max-files 20

  # Skip checkout if sources already exist
  $0 --skip-checkout

  # Use custom dataset
  $0 --dataset my_dataset.json

Environment:
  OPENAI_API_KEY must be set

This will:
1. Download all project sources at correct commits
2. Run baseline analysis on each project
3. Score results against benchmark
4. Generate individual and aggregate reports

EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dataset)
            DATASET="$2"
            shift 2
            ;;
        --max-files)
            MAX_FILES="$2"
            shift 2
            ;;
        --skip-checkout)
            SKIP_CHECKOUT=true
            shift
            ;;
        --skip-baseline)
            SKIP_BASELINE=true
            shift
            ;;
        --skip-scoring)
            SKIP_SCORING=true
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            ;;
        *)
            print_color $RED "Unknown option: $1"
            echo "Use --help for usage"
            exit 1
            ;;
    esac
done

# Check API key
if [ -z "$OPENAI_API_KEY" ]; then
    print_color $RED "Error: OPENAI_API_KEY not set"
    echo "Please run: export OPENAI_API_KEY='your-key'"
    exit 1
fi

# Check dataset exists
if [ ! -f "$DATASET" ]; then
    print_color $RED "Error: Dataset not found: $DATASET"
    exit 1
fi

# Create output directories
SOURCES_DIR="${OUTPUT_DIR}/sources"
BASELINE_DIR="${OUTPUT_DIR}/baseline_results"
SCORES_DIR="${OUTPUT_DIR}/scoring_results"
REPORTS_DIR="${OUTPUT_DIR}/reports"

mkdir -p "$SOURCES_DIR"
mkdir -p "$BASELINE_DIR"
mkdir -p "$SCORES_DIR"
mkdir -p "$REPORTS_DIR"

# Count projects in dataset
PROJECT_COUNT=$(python3 -c "
import json
with open('$DATASET', 'r') as f:
    data = json.load(f)
    print(len(data))
")

print_header "ScaBench Run All - Processing $PROJECT_COUNT Projects"
echo "Dataset:          $DATASET"
echo "Output Directory: $OUTPUT_DIR"
echo "Max Files:        ${MAX_FILES:-all}"
echo ""
echo "Pipeline Steps:"
[ "$SKIP_CHECKOUT" = false ] && echo "  ✓ Source Checkout" || echo "  ✗ Source Checkout (skipped)"
[ "$SKIP_BASELINE" = false ] && echo "  ✓ Baseline Analysis" || echo "  ✗ Baseline Analysis (skipped)"
[ "$SKIP_SCORING" = false ] && echo "  ✓ Scoring & Reports" || echo "  ✗ Scoring & Reports (skipped)"
echo ""

# Step 1: Checkout all sources
if [ "$SKIP_CHECKOUT" = false ]; then
    print_header "Step 1: Downloading All Project Sources"
    
    python dataset-generator/checkout_sources.py \
        --dataset "$DATASET" \
        --output "$SOURCES_DIR"
    
    print_color $GREEN "✓ Source checkout complete"
else
    print_color $YELLOW "Skipping source checkout"
fi

# Step 2: Run baseline on all projects
if [ "$SKIP_BASELINE" = false ]; then
    print_header "Step 2: Running Baseline Analysis on All Projects"
    
    # Get list of all projects
    PROJECTS=$(python3 -c "
import json
with open('$DATASET', 'r') as f:
    data = json.load(f)
    for project in data:
        project_id = project.get('project_id', '').replace('-', '_').replace(' ', '_').lower()
        print(project_id)
")
    
    ANALYZED=0
    FAILED=0
    
    for PROJECT_ID in $PROJECTS; do
        ANALYZED=$((ANALYZED + 1))
        print_color $CYAN "[$ANALYZED/$PROJECT_COUNT] Analyzing: $PROJECT_ID"
        
        # Find source directory
        SOURCE_DIR=""
        for DIR in "$SOURCES_DIR"/*; do
            if [[ $(basename "$DIR") == *"$PROJECT_ID"* ]]; then
                SOURCE_DIR="$DIR"
                break
            fi
        done
        
        if [ -z "$SOURCE_DIR" ] || [ ! -d "$SOURCE_DIR" ]; then
            print_color $YELLOW "  ⚠ Source not found for $PROJECT_ID, skipping"
            FAILED=$((FAILED + 1))
            continue
        fi
        
        # Run baseline analysis
        CMD="python baseline-runner/baseline_runner.py"
        CMD="$CMD --project \"$PROJECT_ID\""
        CMD="$CMD --source \"$SOURCE_DIR\""
        CMD="$CMD --output \"$BASELINE_DIR\""
        CMD="$CMD --model gpt-5-mini"
        [ -n "$MAX_FILES" ] && CMD="$CMD --max-files $MAX_FILES"
        
        if eval $CMD; then
            print_color $GREEN "  ✓ Analysis complete for $PROJECT_ID"
        else
            print_color $RED "  ✗ Analysis failed for $PROJECT_ID"
            FAILED=$((FAILED + 1))
        fi
    done
    
    print_color $GREEN "✓ Baseline analysis complete: $((ANALYZED - FAILED))/$PROJECT_COUNT succeeded"
else
    print_color $YELLOW "Skipping baseline analysis"
fi

# Step 3: Score all results and generate reports
if [ "$SKIP_SCORING" = false ]; then
    print_header "Step 3: Scoring All Results"
    
    # Score all baseline results
    python scoring/scorer.py \
        --benchmark "$DATASET" \
        --results-dir "$BASELINE_DIR" \
        --output "$SCORES_DIR" \
        --model gpt-5-mini
    
    print_color $GREEN "✓ Scoring complete"
    
    print_header "Step 4: Generating Reports"
    
    # Generate main report
    python scoring/report_generator.py \
        --scores "$SCORES_DIR" \
        --output "${REPORTS_DIR}/full_report.html" \
        --tool-name "ScaBench Baseline" \
        --model gpt-5-mini
    
    print_color $GREEN "✓ Report generation complete"
else
    print_color $YELLOW "Skipping scoring and reports"
fi

# Generate summary statistics
print_header "Generating Summary Statistics"

python3 -c "
import json
import os
from pathlib import Path

output_dir = Path('$OUTPUT_DIR')
scores_dir = output_dir / 'scoring_results'
summary_file = output_dir / 'summary.json'

# Collect all scores
all_scores = []
for score_file in scores_dir.glob('score_*.json'):
    with open(score_file, 'r') as f:
        all_scores.append(json.load(f))

if all_scores:
    # Calculate totals
    total_expected = sum(s['total_expected'] for s in all_scores)
    total_tp = sum(s['true_positives'] for s in all_scores)
    total_fn = sum(s['false_negatives'] for s in all_scores)
    total_fp = sum(s['false_positives'] for s in all_scores)
    
    # Calculate rates
    detection_rate = (total_tp / total_expected * 100) if total_expected > 0 else 0
    precision = (total_tp / (total_tp + total_fp) * 100) if (total_tp + total_fp) > 0 else 0
    f1 = (2 * detection_rate * precision / (detection_rate + precision)) if (detection_rate + precision) > 0 else 0
    
    summary = {
        'projects_analyzed': len(all_scores),
        'total_expected': total_expected,
        'total_true_positives': total_tp,
        'total_false_negatives': total_fn,
        'total_false_positives': total_fp,
        'overall_detection_rate': round(detection_rate, 1),
        'overall_precision': round(precision, 1),
        'overall_f1_score': round(f1, 1)
    }
    
    # Save summary
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Print summary
    print(f'📊 Overall Results:')
    print(f'  • Projects Analyzed:  {summary[\"projects_analyzed\"]}')
    print(f'  • Detection Rate:     {summary[\"overall_detection_rate\"]}%')
    print(f'  • Precision:          {summary[\"overall_precision\"]}%')
    print(f'  • F1 Score:           {summary[\"overall_f1_score\"]}%')
    print(f'  • True Positives:     {total_tp}')
    print(f'  • False Negatives:    {total_fn}')
    print(f'  • False Positives:    {total_fp}')
else:
    print('No scoring results found')
"

# Final summary
print_header "✅ ALL DONE!"

echo "📁 Results saved to: $OUTPUT_DIR/"
echo ""
echo "Key Files:"
echo "  • Full Report:     ${REPORTS_DIR}/full_report.html"
echo "  • Summary Stats:   ${OUTPUT_DIR}/summary.json"
echo "  • All Scores:      ${SCORES_DIR}/"
echo "  • Baseline Results: ${BASELINE_DIR}/"
echo ""
echo "To view the report:"
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "  open ${REPORTS_DIR}/full_report.html"
else
    echo "  xdg-open ${REPORTS_DIR}/full_report.html"
fi

print_color $GREEN "Processing complete for ALL $PROJECT_COUNT projects!"