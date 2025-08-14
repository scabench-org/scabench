# Baseline Generator Testing Guide

## Quick Test

Run a single project with evaluation:

```bash
export OPENAI_API_KEY=your_key_here

# Run baseline on a single project
python baseline_runner.py ../datasets/scabench_2025-02_to_2025-08.json \
  --output-dir test_output \
  --project "BitVault" \
  --max-files 10

# Evaluate results
python evaluate_baseline.py test_output ../datasets/scabench_2025-02_to_2025-08.json
```

## Batch Testing

Run multiple projects at once:

```bash
export OPENAI_API_KEY=your_key_here
./run_batch_test.sh
```

This will:
1. Analyze multiple projects (configured in the script)
2. Automatically run evaluation
3. Generate detailed reports

## Understanding the Results

### Evaluation Metrics

The evaluation produces three key metrics:

1. **Found**: Issues that match expected vulnerabilities
2. **Missed**: Expected vulnerabilities not detected
3. **False Positives**: Detected issues that don't match any expected vulnerability

### Output Files

After running evaluation, you'll find:

```
output_dir/
├── *_baseline.json           # Raw baseline results for each project
├── baseline_summary.json     # Summary of all baseline runs
└── evaluation/
    ├── evaluation_summary.json     # Overall evaluation metrics
    └── *_evaluation.json          # Detailed evaluation per project
```

### Evaluation Details

Each project evaluation shows:
- **Score**: Percentage of expected issues found
- **By Severity**: Breakdown of found/expected by severity level
- **Found Issues**: List of matched vulnerabilities with similarity scores
- **Missed Issues**: Expected vulnerabilities that weren't detected
- **False Positives**: Baseline findings with no match

## Interpreting Results

### Good Performance Indicators
- High recall (many expected issues found)
- Low false positive rate
- Good coverage of medium/high severity issues

### Common Patterns
- Baseline is good at finding:
  - Reentrancy vulnerabilities
  - Unchecked external calls
  - Access control issues
  - Integer overflow/underflow

- Baseline may miss:
  - Complex business logic bugs
  - Cross-contract vulnerabilities
  - Subtle decimal/precision issues
  - Economic attacks

## Debugging

### Check Individual Matches

Look at `*_evaluation.json` files to see:
- Why issues matched (similarity scores)
- Which issues were missed
- Details of false positives

### Adjust Thresholds

In `evaluate_baseline.py`, you can adjust:
- Minimum similarity threshold (default: 0.25)
- Severity matching rules
- Keyword boosting for vulnerability terms

## Session Management

The baseline runner supports resuming interrupted runs:

```bash
# First run (may be interrupted)
python baseline_runner.py dataset.json --output-dir results

# Resume from where it left off
python baseline_runner.py dataset.json --output-dir results

# Force fresh start
python baseline_runner.py dataset.json --output-dir results --clear-session
```

## Tips for Better Results

1. **Increase File Limit**: More files = better coverage
   ```bash
   --max-files 20  # Analyze up to 20 files per project
   ```

2. **Use Caching**: Speed up repeated runs
   ```bash
   --cache-dir ~/.baseline_cache
   ```

3. **Filter Projects**: Test specific projects
   ```bash
   --project "project_name"  # Partial match supported
   ```

4. **Verbose Output**: See detailed progress
   ```bash
   --verbose
   ```

## Example Results

A typical evaluation might show:

```
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

This indicates the baseline found about 35% of expected issues, with better performance on high-severity vulnerabilities.