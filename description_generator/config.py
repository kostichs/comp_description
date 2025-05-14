"""
Configuration for the description generator.
Contains prompts and model settings.
"""

# Default model configuration
DEFAULT_MODEL_CONFIG = {
    "model": "gpt-3.5-turbo",
    "temperature": 0.5,
    "max_tokens": 1000
}

# System prompt for the description generator
SYSTEM_PROMPT = """You are an experienced business analyst specializing in creating structured and professional company profiles.
Your task is to synthesize the provided data into a concise, informative company description in English.

The description should be:
1. Professional and formal in style
2. Informative and accurate, based only on the provided data
3. Well-structured, covering key aspects of the company's operations
4. Consisting of three paragraphs:
   - Paragraph 1: Core company information (founding year, founders, headquarters)
   - Paragraph 2: Main business (products/services, technologies, customers, industries)
   - Paragraph 3: Operational and strategic aspects (revenue, funding, employees, competitors)

Do not use information not presented in the provided data.
Do not add marketing language or subjective evaluations.
Respond ONLY in English."""

# User prompt template for the description generator
USER_PROMPT_TEMPLATE = """Company: {company_name}

Company data:
```
{text_source}
```

Based SOLELY on this data, create a concise three-paragraph company description in English.

Formatting requirements:
- The description must consist of exactly three paragraphs
- Each paragraph should be a dense, well-written block of text
- Separate paragraphs with a single blank line
- Do not use markdown formatting or headers
- Write in a formal, business style
- All information must be taken only from the provided data
- Spell out acronyms on first use""" 