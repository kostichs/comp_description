# Serper.dev API Integration Guide

## Overview

This guide explains how the criteria evaluation system integrates with the Serper.dev API to gather web-based information about companies for criteria evaluation. This feature allows the system to utilize Google search results when evaluating criteria that require information beyond the company's general description.

## Configuration

The Serper.dev API integration is configured in `config.py`:

```python
# Serper.dev API configuration
SERPER_API_KEY = os.getenv("SERPER_API_KEY")  # API key loaded from .env file
SERPER_API_URL = "https://google.serper.dev/search"  # Serper.dev API endpoint
SERPER_MAX_RETRIES = 3  # Maximum number of retries for failed API calls
SERPER_RETRY_DELAY = 2  # Delay in seconds between retry attempts
DEBUG_SERPER = True  # Enable/disable debug output for Serper API calls
```

Make sure to add your Serper.dev API key to the `.env` file:

```
SERPER_API_KEY=your_api_key_here
```

## Implementation Details

### Core Components

1. **serper_utils.py**
   - Contains all functionality for interacting with the Serper.dev API
   - Handles website URL formatting and cleanup
   - Implements error handling and retries for API calls

2. **criteria_checkers.py**
   - Determines when to use web-based information based on the "Place" column in criteria files
   - Integrates web search results with company descriptions for criteria evaluation

### Key Functions

#### `perform_google_search(query, retries=None)`

Makes API calls to Serper.dev to perform Google searches.

```python
search_results = perform_google_search("microsoft.com sustainability initiatives")
```

Parameters:
- `query`: The search query to send to Serper.dev
- `retries`: Number of retries if API call fails (defaults to value in config)

Returns:
- Dictionary containing search results in JSON format or None if all retries failed

#### `get_information_for_criterion(company_info, place, search_query=None)`

The main function for gathering information based on the criteria's "Place" value.

```python
information, source = get_information_for_criterion(
    company_info,
    "website",
    "{website} sustainability initiatives"
)
```

Parameters:
- `company_info`: Dictionary with company information (must include "Description" and optionally "Official_Website")
- `place`: The "Place" column value from criteria CSV (e.g., "gen_descr", "website")
- `search_query`: Optional search query template if place is "website"

Returns:
- Tuple containing:
  - `information_text`: Text to use for criterion evaluation (description or combined search results)
  - `source_description`: Description of where the information came from

## Search Query Templates

When the "Place" value is "website", the system uses the "Search Query" column from the criteria file. This should be a template string that includes `{website}` which will be replaced with the company's domain.

Example search query templates:
- `{website} api documentation`
- `{website} service level agreement uptime`
- `{website} sustainability initiatives`

## Error Handling

The implementation includes robust error handling:

1. If a company has no valid website, it falls back to using the general description
2. If the Serper.dev API call fails after all retries, it falls back to using the general description
3. If an unexpected error occurs during website URL processing, it logs the error and falls back to general description

## Debugging

When `DEBUG_SERPER` is enabled in config.py, the system outputs detailed information about Serper.dev API calls:

- Search query
- Response status code and size
- Preview of search results (first 3 organic results)

Example debug output:
```
===== SERPER.DEV RESPONSE =====
💡 Search Query: microsoft.com sustainability initiatives
📊 Response status: 200
📄 Response size: 5835 bytes
📊 Found 10 organic results
  1. Sustainability | Microsoft CSR
     URL: https://www.microsoft.com/en-us/corporate-responsibility/sustainability
     Snippet: Discover how we're accelerating progress toward a sustainable future...
  2. Microsoft Sustainability - Products for a Sustainable Future
     URL: https://www.microsoft.com/en-us/sustainability
     Snippet: Microsoft is working to make datacenters and AI systems more energy...
=================================
```

## Testing

For testing the Serper.dev API integration:

1. **test_serper.py**: Simple script to test direct API calls to Serper.dev
2. **test_company_criterion.py**: Tests the `get_information_for_criterion` function with sample company data
3. **test_full_flow.py**: End-to-end test of the full criteria evaluation flow with real company data

## Best Practices

1. **Minimize API calls**: Serper.dev API calls are expensive, so avoid unnecessary calls
2. **Use specific search queries**: Create search queries that are specific to the criterion being evaluated
3. **Handle rate limits**: Be aware of Serper.dev API rate limits and implement appropriate measures
4. **Keep API keys secure**: Never commit API keys to version control

## Troubleshooting

Common issues:

1. **API key issues**: Make sure your API key is correctly set in the `.env` file
2. **Rate limiting**: If you encounter 429 errors, you've hit the API rate limit
3. **Invalid search queries**: Ensure search queries are well-formatted and include the {website} placeholder
4. **Network issues**: Check your internet connection if API calls consistently fail 