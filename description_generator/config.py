"""
Configuration for the description generator.
Contains prompts and model settings.
"""

# Default model configuration
DEFAULT_MODEL_CONFIG = {
    "model": "gpt-4o-mini",
    "temperature": 0.3,
}

# System prompt for the description generator
SYSTEM_PROMPT = """You are an experienced business analyst specializing in extracting structured information and creating professional company profiles.
Your task is to help identify key business information from unstructured text, following a structured extraction approach.

Use a meticulous approach to analyze the provided company information:
1. Extract key details about the company's foundation, leadership, products, market, and operations
2. Organize the information into appropriate categories
3. Fill in all required fields with the most accurate information available
4. If specific information is not available, indicate this clearly

Your output will be used to generate a comprehensive company profile that is:
- Factually accurate based on the provided data
- Well-structured and organized
- Professional in tone and presentation

Stick strictly to the information provided in the input text. Do not fabricate or assume facts not explicitly stated."""

# User prompt template for the description generator
USER_PROMPT_TEMPLATE = """Company: {company_name}

Company data:
```
{text_source}
```

Please analyze the above information about {company_name} and extract key structured data points about the company.

Focus on extracting:
1. Basic company information (founding year, location, founders)
2. Core business details (products/services, technologies used)
3. Market information (customer types, industries served, geographic markets)
4. Financial and operational details
5. Strategic information (major clients, partnerships, competitors)

Use the data to build a detailed understanding of the company's profile.""" 