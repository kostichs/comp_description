# New Structure of Company Description Generator Project

## Overview
This project has been restructured to improve code maintainability, fix formatting issues in large files, and simplify adding new integrations and features.

## Directory Structure

```
company-description/
│
├── src/                        # Main project code
│   ├── pipeline/               # Main pipeline module
│   │   ├── __init__.py         # Exports public API
│   │   ├── adapter.py          # Main PipelineAdapter class
│   │   ├── core.py             # Core process functions
│   │   └── utils/              # Utility functions
│   │       ├── __init__.py     
│   │       ├── logging.py      # Logging configuration
│   │       └── markdown.py     # Report functions
│   │
│   ├── integrations/           # External integrations
│   │   ├── __init__.py
│   │   └── hubspot/            # HubSpot integration
│   │       ├── __init__.py
│   │       ├── adapter.py      # HubSpotPipelineAdapter
│   │       ├── client.py       # HubSpotClient for API
│   │       └── service.py      # HubSpotIntegrationService
│   │
│   ├── config.py               # Project configuration
│   └── data_io.py              # Data input/output functions
│
├── run_pipeline.py             # Entry point for running pipeline
├── llm_config.yaml             # LLM configuration
└── .env                        # API keys and environment variables
```

## Major Changes

### 1. Modular Structure
- Large file `pipeline_adapter.py` split into several smaller modules
- Code grouped by functionality (pipeline, integrations)
- Entry point extracted to separate file `run_pipeline.py`

### 2. Object-Oriented Approach
- Main code rewritten as classes
- `PipelineAdapter` - base class for pipeline operations
- `HubSpotPipelineAdapter` - extension with HubSpot support

### 3. Integrations
- External integrations separated into dedicated directory
- HubSpot integration fully encapsulated

## Usage

### Running Pipeline
```bash
python run_pipeline.py --input companies.csv --config llm_config.yaml
```

### Command Line Options
- `--input` / `-i`: Path to input CSV file (default: test_companies.csv)
- `--config` / `-c`: Path to configuration file (default: llm_config.yaml)
- `--use-hubspot`: Enable HubSpot integration
- `--disable-hubspot`: Disable HubSpot integration

### HubSpot Integration
For HubSpot integration to work:
1. Add API key to `.env` file: `HUBSPOT_API_KEY=your_api_key_here`
2. Enable integration in `llm_config.yaml`:
```yaml
use_hubspot_integration: true
hubspot_description_max_age_months: 6
```

## Development

### Adding New Integrations
1. Create new directory in `src/integrations/`
2. Create API client in `client.py`
3. Implement business logic in `service.py`
4. Create pipeline extension in `adapter.py`
5. Update factory in `src/pipeline/__init__.py`

### Adding New Finders
1. Implement new Finder in `finders/`
2. Add it to `PipelineAdapter` 