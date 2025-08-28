# ScaBench Dataset Generator

A comprehensive system for generating and curating security audit datasets from multiple platforms. This toolkit consists of two main components:

1. **Scraper**: Extracts security audit data from platforms like Code4rena, Cantina, and Sherlock
2. **Curator**: Filters and enriches the scraped data based on configurable quality criteria

The system extracts vulnerability findings, GitHub repository information, and project metadata to create structured datasets for security research.

## Installation

```bash
pip install -r requirements.txt

# For code analysis features (optional)
brew install cloc  # macOS
apt-get install cloc  # Ubuntu/Debian
```

## Workflow Overview

The typical workflow for generating a curated dataset:

1. **Scrape**: Use `scraper.py` to collect audit data from various platforms
2. **Curate**: Use `curate_dataset.py` to filter and enrich the scraped data

```bash
# Step 1: Scrape data from platforms (last 6 months)
python scraper.py --months 6 --output raw_dataset.json

# Step 2: Curate the dataset (filter by quality criteria)
python curate_dataset.py -i raw_dataset.json -o curated_dataset.json

# With custom criteria
python curate_dataset.py -i raw_dataset.json -o curated_dataset.json \
    --min-vulnerabilities 10 --min-high-critical 2
```

## Component 1: Scraper

The scraper extracts raw audit data from various platforms. For detailed scraper documentation, see the sections below.

## Component 2: Dataset Curator (`curate_dataset.py`)

The curator filters and validates scraped data to ensure high-quality benchmark datasets.

### Curation Features

- **Quality Filtering**: Removes projects with insufficient vulnerabilities
- **GitHub Validation**: Verifies repository accessibility
- **Data Enrichment**: Adds metadata and statistics
- **Report Generation**: Creates detailed markdown reports

### Command Line Usage

```bash
# Basic usage
python curate_dataset.py -i raw_dataset.json -o curated_dataset.json

# With custom filtering criteria
python curate_dataset.py \
  -i raw_dataset.json \
  -o curated_dataset.json \
  --min-vulnerabilities 5 \
  --min-high-critical 1 \
  --report curation_report.md

# Parameters:
#   -i, --input:             Input JSON dataset from scraper
#   -o, --output:            Output curated JSON file
#   -r, --report:            Markdown report file (default: curation_report.md)
#   --min-vulnerabilities:   Min total vulnerabilities required (default: 5)
#   --min-high-critical:     Min high/critical vulnerabilities (default: 1)
```

### Curation Criteria

Projects are filtered based on:

1. **Vulnerability Count**: Must have ≥ min-vulnerabilities
2. **Severity**: Must have ≥ min-high-critical high or critical findings
3. **Repository Access**: GitHub repo must be accessible
4. **Data Completeness**: Must have valid vulnerability descriptions

### Output Format

The curator produces:
- **Curated Dataset**: Filtered JSON with only high-quality projects
- **Markdown Report**: Statistics about the curation process including:
  - Projects filtered and reasons
  - Language distribution
  - Severity breakdown
  - Platform statistics

## Component 3: Scraper Details

### Command Line

```bash
# Scrape all platforms for the last 12 months
python scraper.py

# Scrape specific platforms
python scraper.py --platforms code4rena cantina

# Scrape last 6 months
python scraper.py --months 6

# Custom output file
python scraper.py --output my_dataset.json

# Test mode with local data
python scraper.py --test-mode --test-data-dir test/testdata

# List available platforms
python scraper.py --list-platforms

# Verbose output for debugging
python scraper.py --verbose

### Programmatic Usage

```python
from scraper import ScraperOrchestrator
from datetime import datetime

orchestrator = ScraperOrchestrator()
dataset = orchestrator.scrape(
    platforms=['code4rena', 'sherlock'],
    months=6
)
```

## Architecture

### Core Components

- **`base_scraper.py`**: Abstract base class defining the scraper interface
- **`models.py`**: Data models (Dataset, Project, Codebase, Vulnerability)
- **`scraper_factory.py`**: Factory pattern for scraper registration and creation
- **`scraper.py`**: Main orchestrator that coordinates scraping across platforms

### Platform Scrapers

Each platform has its own scraper implementation in the `scrapers/` directory:

- **`code4rena_scraper.py`**: Scrapes Code4rena HTML reports
- **`sherlock_scraper.py`**: Scrapes Sherlock PDF reports from GitHub
- **`cantina_scraper.py`**: Scrapes Cantina HTML portfolio

### Adding a New Platform

1. Create a new scraper class inheriting from `BaseScraper`
2. Implement `fetch_contests()` and `fetch_report()` methods
3. Use the `@register_scraper("platform_name")` decorator
4. Place the file in the `scrapers/` directory

Example:

```python
from base_scraper import BaseScraper
from scraper_factory import register_scraper

@register_scraper("new_platform")
class NewPlatformScraper(BaseScraper):
    def fetch_contests(self, period_start, period_end):
        # Fetch list of contests in date range
        pass
    
    def fetch_report(self, contest_id):
        # Fetch and parse individual report
        pass
```

## Output Format

The scraper produces a JSON file with the following structure:

```json
{
  "dataset_id": "scabench_2024-01_to_2024-12",
  "period_start": "2024-01-01",
  "period_end": "2024-12-31",
  "schema_version": "1.0.0",
  "projects": [
    {
      "project_id": "code4rena_project-name_2024_03",
      "name": "Project Name",
      "platform": "code4rena",
      "codebases": [
        {
          "codebase_id": "project_abc123",
          "repo_url": "https://github.com/org/repo",
          "commit": "abc123...",
          "tree_url": "https://github.com/org/repo/tree/abc123..."
        }
      ],
      "vulnerabilities": [
        {
          "finding_id": "code4rena_project_H-01",
          "severity": "high",
          "title": "Vulnerability Title",
          "description": "..."
        }
      ]
    }
  ]
}
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--platforms` | Platforms to scrape (code4rena, cantina, sherlock) | All platforms |
| `--months` | Number of months to look back from today | 12 |
| `--output` | Output filename | Auto-generated |
| `--output-dir` | Output directory | `datasets` |
| `--verbose` | Enable verbose logging | False |
| `--test-mode` | Run in test mode with local data | False |
| `--test-data-dir` | Directory containing test data | `test/testdata` |
| `--list-platforms` | List available platforms and exit | - |

## Component 2: Curator

The curator filters the scraped dataset based on quality criteria and enriches it with code metrics.

### Features

- **Repository Validation**: Checks if GitHub repositories exist (not 404)
- **Vulnerability Filtering**: Filters projects by minimum vulnerability counts
- **Code Analysis**: Adds lines of code statistics using `cloc` (when available)
- **Report Generation**: Creates detailed markdown reports of the curation process

### Command Line Options

```bash
python curate_dataset.py -i INPUT -o OUTPUT [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `-i, --input` | Path to input JSON dataset file | Required |
| `-o, --output` | Path to output curated JSON file | Required |
| `-r, --report` | Path to output report file | `curation_report.md` |
| `--min-vulnerabilities` | Minimum total vulnerabilities required | 5 |
| `--min-high-critical` | Minimum high/critical vulnerabilities required | 1 |

### Curation Criteria

Projects are included in the curated dataset if they meet ALL of the following:

1. **Repository Availability**: At least one GitHub repository that exists (not returning 404)
2. **Vulnerability Count**: Minimum number of total vulnerabilities (configurable, default: 5)
3. **Severity Threshold**: Minimum number of high or critical findings (configurable, default: 1)
4. **Code Metrics**: CLOC statistics added when repository can be cloned (optional - failures don't exclude projects)

### Example Usage

```bash
# Basic curation with defaults
python curate_dataset.py -i datasets/raw_data.json -o datasets/curated.json

# Strict criteria: require 10+ vulnerabilities with 3+ high/critical
python curate_dataset.py -i raw.json -o strict.json \
    --min-vulnerabilities 10 --min-high-critical 3

# Custom report location
python curate_dataset.py -i raw.json -o curated.json \
    --report analysis/curation_report.md
```

### Output

The curator produces:
1. **Curated JSON dataset**: Filtered subset of input data
2. **Markdown report**: Detailed statistics and project listings including:
   - Summary statistics (retention rate, total LoC, vulnerability counts)
   - Per-project details (repositories, vulnerability breakdown, code metrics)
   - Language breakdown for each project

## Testing

Run the test suite:

```bash
# Run all tests
python test/test_scrapers.py

# Run with verbose output
python test/test_scrapers.py -v

# Run specific test class
python -m unittest test.test_scrapers.TestCode4renaScraper
```