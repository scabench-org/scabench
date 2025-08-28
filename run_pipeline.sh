#!/bin/bash
#
# ScaBench Master Pipeline Script
# Run the complete analysis pipeline with one command
#
# Usage:
#   ./run_pipeline.sh --project PROJECT_NAME --source SOURCE_DIR [OPTIONS]
#
# Options:
#   --project NAME       Project name/identifier
#   --source DIR         Source code directory
#   --benchmark FILE     Benchmark dataset file (default: datasets/curated-2025-08-18.json)
#   --max-files N        Maximum files to analyze (default: all)
#   --analysis-model M   Model for analysis (default: gpt-5-mini)
#   --scoring-model M    Model for scoring (default: gpt-4o)
#   --output-dir DIR     Output directory (default: pipeline_results/PROJECT_NAME/)
#   --skip-analysis      Skip analysis step (use existing results)
#   --skip-scoring       Skip scoring step
#   --skip-report        Skip report generation
#   --verbose            Show detailed output
#   --help               Show this help message
#

set -e  # Exit on error

# Default values
BENCHMARK="datasets/curated-2025-08-18.json"
ANALYSIS_MODEL="gpt-5-mini"
SCORING_MODEL="gpt-4o"
MAX_FILES=""
VERBOSE=false
SKIP_ANALYSIS=false
SKIP_SCORING=false
SKIP_REPORT=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_color() {
    color=$1
    shift
    echo -e "${color}$@${NC}"
}

# Function to print section headers
print_header() {
    echo ""
    print_color $CYAN "======================================="
    print_color $CYAN "$1"
    print_color $CYAN "======================================="
    echo ""
}

# Function to show help
show_help() {
    echo "ScaBench Master Pipeline Script"
    echo ""
    echo "Usage:"
    echo "  $0 --project PROJECT_NAME --source SOURCE_DIR [OPTIONS]"
    echo ""
    echo "Required Arguments:"
    echo "  --project NAME       Project name/identifier"
    echo "  --source DIR         Source code directory containing contracts"
    echo ""
    echo "Optional Arguments:"
    echo "  --benchmark FILE     Benchmark dataset file (default: datasets/curated-2025-08-18.json)"
    echo "  --max-files N        Maximum files to analyze (default: all)"
    echo "  --analysis-model M   Model for analysis (default: gpt-5-mini)"
    echo "  --scoring-model M    Model for scoring (default: gpt-5-mini)"
    echo "  --output-dir DIR     Output directory (default: pipeline_results/PROJECT_NAME/)"
    echo "  --skip-analysis      Skip analysis step (use existing results)"
    echo "  --skip-scoring       Skip scoring step"
    echo "  --skip-report        Skip report generation"
    echo "  --verbose            Show detailed output"
    echo "  --help               Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  OPENAI_API_KEY       Required for LLM-based analysis"
    echo ""
    echo "Examples:"
    echo "  # Basic usage"
    echo "  $0 --project my_project --source ./contracts"
    echo ""
    echo "  # With custom models and file limit"
    echo "  $0 --project my_project --source ./contracts --max-files 20 --analysis-model gpt-4o"
    echo ""
    echo "  # Skip analysis and just score existing results"
    echo "  $0 --project my_project --source ./contracts --skip-analysis"
    echo ""
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --project)
            PROJECT_NAME="$2"
            shift 2
            ;;
        --source)
            SOURCE_DIR="$2"
            shift 2
            ;;
        --benchmark)
            BENCHMARK="$2"
            shift 2
            ;;
        --max-files)
            MAX_FILES="$2"
            shift 2
            ;;
        --analysis-model)
            ANALYSIS_MODEL="$2"
            shift 2
            ;;
        --scoring-model)
            SCORING_MODEL="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_BASE="$2"
            shift 2
            ;;
        --skip-analysis)
            SKIP_ANALYSIS=true
            shift
            ;;
        --skip-scoring)
            SKIP_SCORING=true
            shift
            ;;
        --skip-report)
            SKIP_REPORT=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            show_help
            ;;
        *)
            print_color $RED "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "$PROJECT_NAME" ]; then
    print_color $RED "Error: --project is required"
    echo "Use --help for usage information"
    exit 1
fi

if [ -z "$SOURCE_DIR" ] && [ "$SKIP_ANALYSIS" = false ]; then
    print_color $RED "Error: --source is required (unless using --skip-analysis)"
    echo "Use --help for usage information"
    exit 1
fi

# Check for OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    print_color $RED "Error: OPENAI_API_KEY environment variable not set"
    echo "Please set it with: export OPENAI_API_KEY='your-key-here'"
    exit 1
fi

# Set default output directory if not specified
if [ -z "$OUTPUT_BASE" ]; then
    OUTPUT_BASE="pipeline_results/${PROJECT_NAME}"
fi

# Create output directories
BASELINE_DIR="${OUTPUT_BASE}/baseline"
SCORING_DIR="${OUTPUT_BASE}/scores"
REPORT_FILE="${OUTPUT_BASE}/report.html"

mkdir -p "$BASELINE_DIR"
mkdir -p "$SCORING_DIR"

# Print configuration
print_header "ScaBench Pipeline Configuration"
echo "Project Name:     $PROJECT_NAME"
if [ "$SKIP_ANALYSIS" = false ]; then
    echo "Source Directory: $SOURCE_DIR"
    echo "Analysis Model:   $ANALYSIS_MODEL"
    [ -n "$MAX_FILES" ] && echo "Max Files:        $MAX_FILES"
fi
echo "Benchmark:        $BENCHMARK"
echo "Scoring Model:    $SCORING_MODEL"
echo "Output Directory: $OUTPUT_BASE"
echo ""
echo "Steps to run:"
[ "$SKIP_ANALYSIS" = false ] && echo "  ✓ Baseline Analysis" || echo "  ✗ Baseline Analysis (skipped)"
[ "$SKIP_SCORING" = false ] && echo "  ✓ Scoring" || echo "  ✗ Scoring (skipped)"
[ "$SKIP_REPORT" = false ] && echo "  ✓ Report Generation" || echo "  ✗ Report Generation (skipped)"
echo ""

# Step 1: Baseline Analysis
if [ "$SKIP_ANALYSIS" = false ]; then
    print_header "Step 1: Running Baseline Analysis"
    
    # Check if source directory exists
    if [ ! -d "$SOURCE_DIR" ]; then
        print_color $RED "Error: Source directory not found: $SOURCE_DIR"
        exit 1
    fi
    
    # Build command
    CMD="python baseline-runner/baseline_runner.py"
    CMD="$CMD --project \"$PROJECT_NAME\""
    CMD="$CMD --source \"$SOURCE_DIR\""
    CMD="$CMD --output \"$BASELINE_DIR\""
    CMD="$CMD --model \"$ANALYSIS_MODEL\""
    [ -n "$MAX_FILES" ] && CMD="$CMD --max-files $MAX_FILES"
    
    if [ "$VERBOSE" = true ]; then
        print_color $BLUE "Running: $CMD"
    fi
    
    eval $CMD
    
    if [ $? -eq 0 ]; then
        print_color $GREEN "✓ Baseline analysis complete"
    else
        print_color $RED "✗ Baseline analysis failed"
        exit 1
    fi
else
    print_color $YELLOW "Skipping baseline analysis (using existing results)"
fi

# Check if baseline results exist
BASELINE_RESULT="${BASELINE_DIR}/baseline_${PROJECT_NAME}.json"
if [ ! -f "$BASELINE_RESULT" ]; then
    print_color $RED "Error: Baseline results not found: $BASELINE_RESULT"
    echo "Please run analysis first or check the output directory"
    exit 1
fi

# Step 2: Scoring
if [ "$SKIP_SCORING" = false ]; then
    print_header "Step 2: Scoring Results Against Benchmark"
    
    # Check if benchmark file exists
    if [ ! -f "$BENCHMARK" ]; then
        print_color $RED "Error: Benchmark file not found: $BENCHMARK"
        exit 1
    fi
    
    # Build command
    CMD="python scoring/scorer.py"
    CMD="$CMD --benchmark \"$BENCHMARK\""
    CMD="$CMD --results \"$BASELINE_RESULT\""
    CMD="$CMD --output \"$SCORING_DIR\""
    CMD="$CMD --model \"$SCORING_MODEL\""
    [ "$VERBOSE" = true ] && CMD="$CMD --verbose"
    
    if [ "$VERBOSE" = true ]; then
        print_color $BLUE "Running: $CMD"
    fi
    
    eval $CMD
    
    if [ $? -eq 0 ]; then
        print_color $GREEN "✓ Scoring complete"
    else
        print_color $RED "✗ Scoring failed"
        exit 1
    fi
else
    print_color $YELLOW "Skipping scoring"
fi

# Check if scoring results exist
if [ ! -d "$SCORING_DIR" ] || [ -z "$(ls -A $SCORING_DIR)" ]; then
    print_color $YELLOW "Warning: No scoring results found in $SCORING_DIR"
    if [ "$SKIP_REPORT" = false ]; then
        print_color $YELLOW "Skipping report generation (no scores to report)"
        SKIP_REPORT=true
    fi
fi

# Step 3: Report Generation
if [ "$SKIP_REPORT" = false ]; then
    print_header "Step 3: Generating HTML Report"
    
    # Build command
    CMD="python scoring/report_generator.py"
    CMD="$CMD --scores \"$SCORING_DIR\""
    CMD="$CMD --output \"$REPORT_FILE\""
    CMD="$CMD --tool-name \"ScaBench Pipeline\""
    CMD="$CMD --tool-version \"v1.0\""
    CMD="$CMD --model \"$ANALYSIS_MODEL\""
    
    if [ "$VERBOSE" = true ]; then
        print_color $BLUE "Running: $CMD"
    fi
    
    eval $CMD
    
    if [ $? -eq 0 ]; then
        print_color $GREEN "✓ Report generation complete"
    else
        print_color $RED "✗ Report generation failed"
        exit 1
    fi
else
    print_color $YELLOW "Skipping report generation"
fi

# Summary
print_header "Pipeline Complete!"

echo "Results saved to: $OUTPUT_BASE/"
echo ""
echo "📁 Output Files:"
echo "  • Baseline Results: $BASELINE_RESULT"
[ -f "${SCORING_DIR}/score_${PROJECT_NAME}.json" ] && echo "  • Scoring Results:  ${SCORING_DIR}/score_${PROJECT_NAME}.json"
[ -f "$REPORT_FILE" ] && echo "  • HTML Report:      $REPORT_FILE"

# Show quick stats if scoring was done
if [ -f "${SCORING_DIR}/score_${PROJECT_NAME}.json" ]; then
    echo ""
    echo "📊 Quick Stats:"
    
    # Extract key metrics using Python (more reliable than jq)
    python3 -c "
import json
with open('${SCORING_DIR}/score_${PROJECT_NAME}.json', 'r') as f:
    data = json.load(f)
    print(f'  • Detection Rate: {data.get(\"detection_rate\", 0)*100:.1f}%')
    print(f'  • Precision:      {data.get(\"precision\", 0)*100:.1f}%')
    print(f'  • F1 Score:       {data.get(\"f1_score\", 0)*100:.1f}%')
    print(f'  • True Positives: {data.get(\"true_positives\", 0)}')
    print(f'  • False Negatives: {data.get(\"false_negatives\", 0)}')
    print(f'  • False Positives: {data.get(\"false_positives\", 0)}')
" 2>/dev/null || echo "  (Could not parse scoring results)"
fi

# Suggest opening the report
if [ -f "$REPORT_FILE" ]; then
    echo ""
    echo "🌐 To view the HTML report, run:"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  open \"$REPORT_FILE\""
    else
        echo "  xdg-open \"$REPORT_FILE\""
    fi
fi

echo ""
print_color $GREEN "✅ All done! Happy auditing!"