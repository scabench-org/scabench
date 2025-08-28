# ScaBench Datasets

## Official Datasets

### Current Dataset: `curated-2025-08-18.json`

**Statistics:**
- **Projects**: 31 high-quality smart contract projects
- **Vulnerabilities**: 555 real findings from audits
- **High/Critical**: 114 severe vulnerabilities
- **Platforms**: Code4rena, Cantina, Sherlock
- **Time Period**: August 2024 - August 2025
- **Total LoC**: 3.3M lines
- **Solidity LoC**: 267K lines

**Curation Criteria:**
- ✅ Publicly accessible GitHub repositories
- ✅ At least 5 vulnerabilities per project
- ✅ At least 1 high/critical severity finding
- ✅ Recent audits (within last year)
- ✅ Commit hash available for reproducibility

## Dataset Format

Each dataset is a JSON file containing an array of projects:

```json
[
  {
    "project_id": "unique_identifier",
    "name": "Human-readable project name",
    "platform": "code4rena|cantina|sherlock",
    "codebases": [
      {
        "codebase_id": "unique_codebase_id",
        "repo_url": "https://github.com/org/repo",
        "commit": "exact_commit_hash",
        "tree_url": "GitHub tree URL at commit",
        "tarball_url": "Direct download URL"
      }
    ],
    "vulnerabilities": [
      {
        "finding_id": "unique_finding_id",
        "severity": "critical|high|medium|low",
        "title": "Clear vulnerability description",
        "description": "Detailed explanation including impact and exploit scenario",
        "location": "Contract.sol:functionName() or line numbers"
      }
    ]
  }
]
```

## Field Descriptions

### Project Fields
- `project_id`: Unique identifier for the project
- `name`: Display name of the project
- `platform`: Audit platform source
- `codebases`: Array of code repositories to analyze
- `vulnerabilities`: Array of known vulnerabilities

### Codebase Fields
- `repo_url`: GitHub repository URL
- `commit`: Exact commit hash to checkout
- `tree_url`: Browse code at this commit
- `tarball_url`: Direct download of code

### Vulnerability Fields
- `finding_id`: Unique identifier (usually platform_report_id)
- `severity`: Standard severity level
- `title`: Short, clear description
- `description`: Full details including:
  - What the vulnerability is
  - How it can be exploited
  - Impact on the system
  - Sometimes includes proof of concept
- `location`: Where the issue exists (as specific as possible)

## Using Datasets

### 1. List Available Projects

```python
import json

with open('curated-2025-08-18.json', 'r') as f:
    dataset = json.load(f)
    
for project in dataset:
    print(f"{project['project_id']}: {project['name']} ({len(project['vulnerabilities'])} vulns)")
```

### 2. Download Source Code

```bash
# Download all projects at exact commits
python ../dataset-generator/checkout_sources.py \
  --dataset curated-2025-08-18.json \
  --output ../sources/
```

### 3. Access Vulnerability Data

```python
# Get all high/critical vulnerabilities
high_critical = []
for project in dataset:
    for vuln in project['vulnerabilities']:
        if vuln['severity'] in ['high', 'critical']:
            high_critical.append({
                'project': project['name'],
                'title': vuln['title'],
                'severity': vuln['severity']
            })
```

## Creating New Datasets

### Option 1: Use the Dataset Generator

```bash
cd ../dataset-generator
python scraper.py \
  --platforms code4rena cantina sherlock \
  --months 3 \
  --output ../datasets/new_dataset.json
```

### Option 2: Manual Curation

1. Start with scraper output
2. Filter projects based on criteria
3. Verify repository accessibility
4. Ensure commit hashes are valid
5. Clean and normalize vulnerability descriptions

### Validation Checklist

Before using a new dataset:
- [ ] All repository URLs are accessible
- [ ] All commit hashes exist and are reachable
- [ ] Vulnerability descriptions are clear and specific
- [ ] Severity levels use standard terms
- [ ] No duplicate vulnerabilities within projects
- [ ] Project IDs are unique across dataset

## Dataset Quality Metrics

**Good Dataset Characteristics:**
- Recent audits (avoid memorization by LLMs)
- Mix of severity levels
- Various vulnerability types
- Different contract types (DeFi, NFT, DAO, etc.)
- Clear vulnerability descriptions with locations

**Current Dataset Distribution:**
- Critical: 20 vulnerabilities
- High: 94 vulnerabilities  
- Medium: 260 vulnerabilities
- Low: 181 vulnerabilities

## Contributing Datasets

To contribute a new dataset:

1. Follow the exact JSON format
2. Include all required fields
3. Verify all repositories are accessible
4. Test with checkout_sources.py
5. Document curation process
6. Submit with statistics (projects, vulns, severity distribution)

## Historical Datasets

As new datasets are created, older ones will be archived here with version numbers and creation dates for reproducibility of past evaluations.