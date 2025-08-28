# ScaBench Quick Start Guide

## The Easiest Way: Run Everything for ALL Projects

### 1️⃣ Setup (One Time)
```bash
# Install dependencies
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY="your-key-here"
```

### 2️⃣ Run Everything
```bash
# Process ALL 31 projects from the dataset
./run_all.sh
```

That's it! This single command will:
- ✅ Download all project source code at exact commits
- ✅ Run baseline security analysis on each project
- ✅ Score results against the benchmark
- ✅ Generate beautiful HTML reports

### 3️⃣ View Results
```bash
# Open the main report
open all_results_*/reports/full_report.html  # macOS
xdg-open all_results_*/reports/full_report.html  # Linux
```

## What You Get

After running `./run_all.sh`, you'll have:

```
all_results_20240828_143022/
├── sources/               # All downloaded project code
│   ├── project1/
│   ├── project2/
│   └── ...
├── baseline_results/      # Security findings for each project
│   ├── baseline_project1.json
│   ├── baseline_project2.json
│   └── ...
├── scoring_results/       # Scoring against benchmark
│   ├── score_project1.json
│   ├── score_project2.json
│   └── ...
├── reports/              
│   └── full_report.html  # 📊 Main report with all metrics
└── summary.json          # Overall statistics
```

## Options for Faster Testing

```bash
# Limit to 10 files per project (faster)
./run_all.sh --max-files 10

# Skip source download if already have them
./run_all.sh --skip-checkout

# Use existing baseline results
./run_all.sh --skip-baseline
```

## Process Specific Projects

If you want to analyze just one project:

```bash
# Download source for one project
python dataset-generator/checkout_sources.py --project vulnerable_vault

# Run pipeline for that project
./run_pipeline.sh --project vulnerable_vault --source sources/vulnerable_vault
```

## Batch Processing Custom Projects

Have your own projects to test?

```bash
# Put all projects in a directory
mkdir my_projects
cp -r project1 my_projects/
cp -r project2 my_projects/

# Process them all
./batch_process.sh my_projects/
```

## Performance Expectations

Running ALL 31 projects:
- **Time**: ~30-60 minutes (depending on API speed)
- **API Calls**: ~500-1000 (depending on project sizes)
- **Cost**: ~$5-10 in API fees
- **Output Size**: ~50MB (including downloaded sources)

With `--max-files 10`:
- **Time**: ~10-20 minutes
- **Cost**: ~$2-5

## Troubleshooting

### "OPENAI_API_KEY not set"
```bash
export OPENAI_API_KEY="sk-..."  # Get from OpenAI dashboard
```

### "Dataset not found"
```bash
# Make sure you're in the scabench directory
cd benchmarks/scabench
./run_all.sh
```

### "Permission denied"
```bash
# Make scripts executable
chmod +x *.sh
```

### Rate Limits
If you hit rate limits, the script will show errors. Wait a bit and resume:
```bash
./run_all.sh --skip-checkout --skip-baseline  # Continue from scoring
```

## Summary

**To baseline and score ALL projects from the dataset:**

```bash
./run_all.sh
```

It's that easy! 🎉

The script handles everything automatically:
- Downloads sources at correct commits
- Runs analysis on all projects
- Scores against benchmark
- Generates comprehensive reports

No need to run anything else - just one command does it all!