# SCABench
A framework for evaluating AI code analysis contract audit agents using recent real-world data.

## Components

### Dataset Generator
A comprehensive scraper system for extracting security audit data from multiple platforms.

- **Location**: [`/dataset-generator`](./dataset-generator)
- **Purpose**: Collects vulnerability findings, GitHub repositories, and project metadata from Code4rena, Cantina, and Sherlock
- **Features**: 
  - Multi-platform support with 100% extraction accuracy
  - GitHub integration for repository and commit tracking
  - Flexible date filtering and test mode
  - Produces structured JSON datasets for AI training/evaluation

See the [dataset-generator README](./dataset-generator/README.md) for detailed usage instructions.
