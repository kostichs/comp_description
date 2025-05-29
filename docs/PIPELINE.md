# Company Information Search Pipeline Documentation

## System Overview

The pipeline is a modular system for searching company information and generating structured descriptions. The system is designed with extensibility and easy integration of new data sources and information processing methods in mind.

## Two Pipeline Operating Modes

The system supports two operating modes depending on the input file format:

### Mode 1: Input file with one column (company names only)

In this mode, the system works through the full pipeline:
1. **LLMDeepSearchFinder** - used for searching text information and official website URL
2. **HomepageFinder** - searches for official website URL if not found through LLMDeepSearch
3. **LinkedInFinder** - searches for company's LinkedIn page URL
4. **DomainCheckFinder** - attempts to find company website URL if not found by previous methods
5. **Description Generator** - creates structured descriptions based on collected data

### Mode 2: Input file with two columns (company names and official website URLs)

In this mode, the system automatically disables official website search components:
1. **LLMDeepSearchFinder** - used only for searching text information (found URLs are ignored)
2. **LinkedInFinder** - searches for company's LinkedIn page URL
3. **Description Generator** - creates structured descriptions based on collected data

The system automatically detects the presence of a second column in the input file and selects the appropriate operating mode.

## Architecture

The pipeline consists of several key components:

1. **Finders** - modules responsible for searching specific types of company information
2. **Description Generator** - module for creating structured descriptions based on collected data
3. **Result Processor** - processes and saves search results
4. **Orchestrator** - coordinates the work of all pipeline components

### Pipeline Components

#### Finders

Finders are modules inherited from the base `Finder` class (finders/base.py) that implement an asynchronous `find()` method. Each finder specializes in searching for a specific type of information:

- **HomepageFinder**: searches for company's official website
- **LinkedInFinder**: searches for company's LinkedIn page
- **LLMDeepSearchFinder**: uses GPT-4o-mini-search-preview for deep internet information search

All finders follow a unified interface and return results in a standardized format:

```python
{
    "source": "finder_name",
    "result": "found_data",
    "error": "error_information" # optional
}
```

#### Description Generator

The description generator takes data collected by finders and creates structured three-paragraph company descriptions in English. Main components:

- **generator.py**: contains data processing logic and OpenAI API interaction
- **config.py**: contains model configuration and prompts

The generator prioritizes information from LLMDeepSearchFinder, which provides the most complete and current company data.

#### Result Processor

The result processor is responsible for:
- Aggregating data from all finders
- Formatting results
- Saving in JSON and Excel formats
- Logging the search process

#### Orchestrator

The orchestrator coordinates the work of all pipeline components:
- Initializes finders and description generator
- Launches information search asynchronously for each company
- Collects results from all finders
- Passes data to the description generator
- Sends final results to the processor for saving

## Pipeline Operation Principle

1. **Data Loading**:
   - Pipeline reads company list from input file
   - Determines presence of second column with official website URLs
   - Selects appropriate operating mode
   - Creates directories for saving results and logs

2. **Component Initialization**:
   - Creates instances of necessary finders and description generator considering operating mode
   - Loads API keys and configurations

3. **Information Search**:
   - For each company, all active finders are launched asynchronously
   - Results from each finder are aggregated

4. **Description Generation**:
   - Obtained data is passed to the description generator
   - Generator creates a structured company description in English
   - Description is added to search results

5. **Result Saving**:
   - Results are saved in JSON and Excel formats
   - Detailed process logs are generated

## Technology Stack

- **Python 3.10+**: main development language
- **Asyncio**: for asynchronous request execution
- **OpenAI API**: for LLM requests (GPT-3.5-turbo, GPT-4o-mini-search-preview)
- **aiohttp**: for asynchronous HTTP requests
- **BeautifulSoup4**: for HTML content parsing
- **Pandas**: for data processing and export

## How to Add a New Finder

To integrate a new data source, create a new finder by following these steps:

1. **Create a new class** inheriting from the base `Finder` class:

```python
from finders.base import Finder

class NewSourceFinder(Finder):
    def __init__(self, api_key: str = None, verbose: bool = False):
        self.api_key = api_key
        self.verbose = verbose
        
    async def find(self, company_name: str, **context) -> dict:
        # Search implementation
        try:
            # Information search logic
            result = "found_information"
            return {
                "source": "new_source_finder",
                "result": result
            }
        except Exception as e:
            return {
                "source": "new_source_finder",
                "result": None,
                "error": str(e)
            }
```

2. **Add the finder to the orchestrator** (orchestrator.py), importing it and adding to the list of active finders:

```python
from finders.new_source_finder import NewSourceFinder

# In orchestrator initialization method
self.finders = [
    # Existing finders
    HomepageFinder(...),
    LinkedInFinder(...),
    LLMDeepSearchFinder(...),
    # New finder
    NewSourceFinder(api_key=config.get("new_source_api_key"))
]
```

3. **Update result processing** in the description generator if necessary.

## Description Generator Configuration

The description generator is configured through the `description_generator/config.py` file:

- **DEFAULT_MODEL_CONFIG**: OpenAI model settings (model, temperature, etc.)
- **SYSTEM_PROMPT**: system prompt for LLM
- **USER_PROMPT_TEMPLATE**: user prompt template

To change the format or language of generated descriptions, update the corresponding prompts in config.py.

## Running the Pipeline

The pipeline is launched through main.py, which calls the `run_pipeline()` function from src/pipeline.py. Configuration is loaded from .env file and YAML configurations.

```bash
python main.py
```

## Input Files

### Single column file format
```
Company Name
Microsoft
Google
Apple
```

### Two column file format
```
Company Name,Official Website
Microsoft,https://microsoft.com
Google,https://google.com
Apple,https://apple.com
```

## Functionality Extension

### Adding a New Description Generation Method

To add a new description generation method:

1. Create a new module in the description_generator directory or extend existing one
2. Update config.py by adding new settings and prompts
3. Modify the _generate_summary_from_text() method in generator.py or create a new method

### Integration with Other Services

For integration with new API services:

1. Add new service configuration to llm_config.yaml
2. Create a new API client in src/external_apis/
3. Develop a finder that uses this API

## Best Practices

1. **Maintain asynchronicity**: all finders should be asynchronous for optimal performance
2. **Handle errors**: properly handle and log errors, returning structured responses
3. **Follow code standards**: adhere to PEP 8 and document code
4. **Test new components**: create test scripts to verify functionality
5. **Separate configuration from code**: move all settings to separate configuration files

## Conclusion

The company information search pipeline is a flexible, extensible system capable of integrating various data sources and information processing methods. The modular architecture allows easy addition of new components and improvement of existing functions without the need to rework the entire system. 