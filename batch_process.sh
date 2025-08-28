#!/bin/bash
#
# ScaBench Batch Processing Script
# Process multiple projects in one go
#
# Usage:
#   ./batch_process.sh SOURCES_DIR [OPTIONS]
#
# This will process all subdirectories in SOURCES_DIR as separate projects
#

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_color() {
    color=$1
    shift
    echo -e "${color}$@${NC}"
}

# Check arguments
if [ $# -lt 1 ]; then
    echo "ScaBench Batch Processing Script"
    echo ""
    echo "Usage:"
    echo "  $0 SOURCES_DIR [OPTIONS]"
    echo ""
    echo "Arguments:"
    echo "  SOURCES_DIR          Directory containing project subdirectories"
    echo ""
    echo "Options:"
    echo "  --benchmark FILE     Benchmark dataset (default: datasets/curated-2025-08-18.json)"
    echo "  --max-files N        Maximum files per project"
    echo "  --analysis-model M   Model for analysis (default: gpt-5-mini)"
    echo "  --scoring-model M    Model for scoring (default: gpt-4o)"
    echo "  --output-base DIR    Base output directory (default: batch_results/)"
    echo ""
    echo "Example:"
    echo "  $0 ./audit_projects --max-files 20"
    echo ""
    echo "This will process each subdirectory in ./audit_projects as a separate project"
    exit 1
fi

SOURCES_DIR="$1"
shift

# Default values
OUTPUT_BASE="batch_results"
BENCHMARK="datasets/curated-2025-08-18.json"
MAX_FILES=""
ANALYSIS_MODEL="gpt-5-mini"
SCORING_MODEL="gpt-4o"

# Parse additional options
while [[ $# -gt 0 ]]; do
    case $1 in
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
        --output-base)
            OUTPUT_BASE="$2"
            shift 2
            ;;
        *)
            print_color $RED "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check if source directory exists
if [ ! -d "$SOURCES_DIR" ]; then
    print_color $RED "Error: Directory not found: $SOURCES_DIR"
    exit 1
fi

# Check for OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    print_color $RED "Error: OPENAI_API_KEY not set"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_BASE"
SUMMARY_FILE="${OUTPUT_BASE}/batch_summary.json"
SUMMARY_HTML="${OUTPUT_BASE}/batch_summary.html"

# Count projects
PROJECT_COUNT=$(find "$SOURCES_DIR" -maxdepth 1 -type d -not -path "$SOURCES_DIR" | wc -l)

print_color $CYAN "========================================="
print_color $CYAN "   ScaBench Batch Processing"
print_color $CYAN "========================================="
echo ""
echo "Sources Directory: $SOURCES_DIR"
echo "Projects Found:    $PROJECT_COUNT"
echo "Output Directory:  $OUTPUT_BASE"
echo "Benchmark:         $BENCHMARK"
echo ""

# Initialize counters
PROCESSED=0
FAILED=0
FAILED_PROJECTS=""

# Process each project
for PROJECT_DIR in "$SOURCES_DIR"/*; do
    if [ -d "$PROJECT_DIR" ]; then
        PROJECT_NAME=$(basename "$PROJECT_DIR")
        PROCESSED=$((PROCESSED + 1))
        
        print_color $CYAN ""
        print_color $CYAN "[$PROCESSED/$PROJECT_COUNT] Processing: $PROJECT_NAME"
        print_color $CYAN "----------------------------------------"
        
        # Build pipeline command
        CMD="./run_pipeline.sh"
        CMD="$CMD --project \"$PROJECT_NAME\""
        CMD="$CMD --source \"$PROJECT_DIR\""
        CMD="$CMD --benchmark \"$BENCHMARK\""
        CMD="$CMD --output-dir \"${OUTPUT_BASE}/${PROJECT_NAME}\""
        CMD="$CMD --analysis-model \"$ANALYSIS_MODEL\""
        CMD="$CMD --scoring-model \"$SCORING_MODEL\""
        [ -n "$MAX_FILES" ] && CMD="$CMD --max-files $MAX_FILES"
        
        # Run pipeline
        if eval $CMD; then
            print_color $GREEN "✓ Successfully processed $PROJECT_NAME"
        else
            print_color $RED "✗ Failed to process $PROJECT_NAME"
            FAILED=$((FAILED + 1))
            FAILED_PROJECTS="${FAILED_PROJECTS}\n  - ${PROJECT_NAME}"
        fi
    fi
done

# Generate batch summary
print_color $CYAN ""
print_color $CYAN "========================================="
print_color $CYAN "   Batch Processing Complete"
print_color $CYAN "========================================="
echo ""
echo "📊 Summary:"
echo "  • Total Projects:      $PROJECT_COUNT"
echo "  • Successfully Processed: $((PROCESSED - FAILED))"
echo "  • Failed:              $FAILED"

if [ $FAILED -gt 0 ]; then
    echo ""
    print_color $YELLOW "Failed Projects:"
    echo -e "$FAILED_PROJECTS"
fi

# Create aggregate summary JSON
echo ""
echo "Creating aggregate summary..."
python3 -c "
import json
import os
from pathlib import Path

output_base = '${OUTPUT_BASE}'
summary = {
    'total_projects': ${PROJECT_COUNT},
    'processed': ${PROCESSED},
    'failed': ${FAILED},
    'projects': []
}

# Collect results from each project
for project_dir in Path(output_base).iterdir():
    if project_dir.is_dir() and project_dir.name != 'batch_summary':
        score_file = project_dir / 'scores' / f'score_{project_dir.name}.json'
        if score_file.exists():
            with open(score_file, 'r') as f:
                score_data = json.load(f)
                summary['projects'].append({
                    'name': project_dir.name,
                    'detection_rate': score_data.get('detection_rate', 0),
                    'precision': score_data.get('precision', 0),
                    'f1_score': score_data.get('f1_score', 0),
                    'true_positives': score_data.get('true_positives', 0),
                    'false_negatives': score_data.get('false_negatives', 0),
                    'false_positives': score_data.get('false_positives', 0)
                })

# Calculate aggregates
if summary['projects']:
    total_tp = sum(p['true_positives'] for p in summary['projects'])
    total_fn = sum(p['false_negatives'] for p in summary['projects'])
    total_fp = sum(p['false_positives'] for p in summary['projects'])
    total_expected = total_tp + total_fn
    
    summary['aggregate'] = {
        'total_true_positives': total_tp,
        'total_false_negatives': total_fn,
        'total_false_positives': total_fp,
        'overall_detection_rate': (total_tp / total_expected) if total_expected > 0 else 0,
        'overall_precision': (total_tp / (total_tp + total_fp)) if (total_tp + total_fp) > 0 else 0
    }

# Save summary
with open('${SUMMARY_FILE}', 'w') as f:
    json.dump(summary, f, indent=2)

print(f'✓ Summary saved to: ${SUMMARY_FILE}')
"

# Generate aggregate HTML report
echo "Generating aggregate HTML report..."
python3 -c "
import json
from datetime import datetime

with open('${SUMMARY_FILE}', 'r') as f:
    data = json.load(f)

html = '''<!DOCTYPE html>
<html>
<head>
    <title>ScaBench Batch Processing Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; }
        h1 { color: #333; }
        .summary { background: #e8f4f8; padding: 20px; border-radius: 8px; margin: 20px 0; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th { background: #667eea; color: white; padding: 12px; text-align: left; }
        td { padding: 12px; border-bottom: 1px solid #ddd; }
        tr:hover { background: #f5f5f5; }
        .metric { display: inline-block; margin: 10px 20px; }
        .metric-value { font-size: 24px; font-weight: bold; color: #667eea; }
        .metric-label { color: #666; font-size: 14px; }
    </style>
</head>
<body>
    <div class=\"container\">
        <h1>ScaBench Batch Processing Report</h1>
        <p>Generated: ''' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '''</p>
        
        <div class=\"summary\">
            <h2>Overall Summary</h2>
            <div class=\"metric\">
                <div class=\"metric-value\">''' + str(data['processed']) + '''</div>
                <div class=\"metric-label\">Projects Processed</div>
            </div>'''

if 'aggregate' in data:
    html += '''
            <div class=\"metric\">
                <div class=\"metric-value\">''' + f\"{data['aggregate']['overall_detection_rate']*100:.1f}%\" + '''</div>
                <div class=\"metric-label\">Overall Detection Rate</div>
            </div>
            <div class=\"metric\">
                <div class=\"metric-value\">''' + f\"{data['aggregate']['overall_precision']*100:.1f}%\" + '''</div>
                <div class=\"metric-label\">Overall Precision</div>
            </div>'''

html += '''
        </div>
        
        <h2>Project Results</h2>
        <table>
            <thead>
                <tr>
                    <th>Project</th>
                    <th>Detection Rate</th>
                    <th>Precision</th>
                    <th>F1 Score</th>
                    <th>True Positives</th>
                    <th>False Negatives</th>
                    <th>False Positives</th>
                </tr>
            </thead>
            <tbody>'''

for project in data.get('projects', []):
    html += f'''
                <tr>
                    <td>{project['name']}</td>
                    <td>{project['detection_rate']*100:.1f}%</td>
                    <td>{project['precision']*100:.1f}%</td>
                    <td>{project['f1_score']*100:.1f}%</td>
                    <td>{project['true_positives']}</td>
                    <td>{project['false_negatives']}</td>
                    <td>{project['false_positives']}</td>
                </tr>'''

html += '''
            </tbody>
        </table>
    </div>
</body>
</html>'''

with open('${SUMMARY_HTML}', 'w') as f:
    f.write(html)

print(f'✓ HTML report saved to: ${SUMMARY_HTML}')
"

echo ""
print_color $GREEN "✅ Batch processing complete!"
echo ""
echo "📁 Results saved to: $OUTPUT_BASE/"
echo "📊 Batch summary:    $SUMMARY_FILE"
echo "🌐 HTML summary:     $SUMMARY_HTML"
echo ""
echo "To view the summary report:"
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "  open \"$SUMMARY_HTML\""
else
    echo "  xdg-open \"$SUMMARY_HTML\""
fi