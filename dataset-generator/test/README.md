# Test Suite Documentation

## Overview

The test suite provides comprehensive testing for the security audit scraper system, including unit tests for individual components and integration tests for end-to-end workflows.

## Test Structure

```
test/
├── run_tests.py           # Main test runner
├── test_scrapers.py        # Comprehensive scraper tests
├── test_base_scraper.py    # Base scraper class tests
├── test_models.py          # Data model tests
├── test_scraper_factory.py # Factory pattern tests
└── testdata/              # Test data files
    ├── cantina-portfolio.html
    ├── cantina-sonic.html
    ├── codearena-2025-04-virtuals-protocol.html
    ├── codearena-reports.html
    ├── sherlock-audits.html
    └── sherlock-metalend.pdf
```

## Running Tests

### Run All Tests
```bash
# Using the test runner
python test/run_tests.py

# Using unittest directly
python -m unittest discover test/

# Using specific test file
python test/test_scrapers.py
```

### Run Specific Test Classes
```bash
# Test only Code4rena scraper
python -m unittest test.test_scrapers.TestCode4renaScraper

# Test only Cantina scraper
python -m unittest test.test_scrapers.TestCantinaScraper

# Test only Sherlock scraper
python -m unittest test.test_scrapers.TestSherlockScraper

# Test CLI functionality
python -m unittest test.test_scrapers.TestCLI
```

### Run with Verbose Output
```bash
python test/test_scrapers.py -v
```

## Test Coverage

### test_scrapers.py
Main comprehensive test suite covering:

#### TestCode4renaScraper
- `test_vulnerability_extraction_accuracy`: Verifies 100% extraction of all vulnerabilities
- `test_github_url_extraction`: Tests GitHub URL and commit hash extraction
- `test_project_metadata`: Validates project metadata extraction

#### TestCantinaScraper
- `test_vulnerability_extraction_accuracy`: Verifies extraction of all severity levels
- `test_github_url_extraction`: Tests GitHub repository detection
- `test_vulnerability_titles`: Validates vulnerability title extraction

#### TestSherlockScraper
- `test_pdf_parsing`: Tests PDF parsing and vulnerability extraction
- `test_project_name_extraction`: Validates project name extraction from PDF
- `test_github_extraction`: Tests GitHub URL extraction from PDF content

#### TestCLI
- `test_list_platforms`: Tests --list-platforms command
- `test_help`: Tests --help command
- `test_single_platform_scraping`: Tests actual scraping with CLI

#### TestIntegration
- `test_end_to_end_scraping`: Full end-to-end integration test

### test_base_scraper.py
Tests for the abstract base scraper class:
- Abstract method enforcement
- Helper method functionality
- ID normalization methods

### test_models.py
Tests for data models:
- Dataset model serialization
- Project model structure
- Codebase model validation
- Vulnerability model fields

### test_scraper_factory.py
Tests for the factory pattern:
- Scraper registration
- Dynamic scraper creation
- Platform listing

## Test Data

The `testdata/` directory contains sample HTML and PDF files from each platform for testing:

- **Code4rena**: HTML report with 32 vulnerabilities (6 High, 26 Medium)
- **Cantina**: HTML report with 7 vulnerabilities (1 Critical, 1 High, 3 Medium, 2 Informational)
- **Sherlock**: PDF report with 2 vulnerabilities (2 Low)

## Extraction Accuracy

Current test results show 100% extraction accuracy:

| Platform | Expected | Extracted | Accuracy |
|----------|----------|-----------|----------|
| Code4rena | 32 | 32 | 100% |
| Cantina | 7 | 7 | 100% |
| Sherlock | 2 | 2 | 100% |

## Adding New Tests

To add tests for a new scraper:

1. Create test data in `testdata/` directory
2. Add a new test class in `test_scrapers.py`:
```python
class TestNewPlatformScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = NewPlatformScraper(test_mode=True, test_data_dir='test/testdata')
    
    def test_vulnerability_extraction(self):
        # Test vulnerability extraction
        pass
```

3. Run tests to verify: `python test/run_tests.py`

## Continuous Integration

The test suite is designed to be CI/CD friendly:
- Returns proper exit codes (0 for success, 1 for failure)
- Provides verbose output for debugging
- Works with standard Python testing tools
- No external dependencies beyond requirements.txt