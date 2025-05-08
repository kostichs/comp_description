# Company Information Scraper & LLM Description Generator

## 1. Project Overview

This project is a Python script designed to automatically gather information about companies, including their websites, LinkedIn profiles, and Wikipedia pages. It extracts relevant text content from the discovered pages and then generates concise descriptions using OpenAI models, flexibly configured via a YAML file.

**Key Features:**
*   Processes a list of companies from `.xlsx` or `.csv` files.
*   Uses the Serper.dev API to find company URLs (main website, LinkedIn, Wikipedia).
*   Employs an LLM (OpenAI) to select the most relevant homepage URL from Serper search results.
*   Utilizes the `wikipedia-api` library to fetch the summary of the Wikipedia article.
*   Attempts to find and extract text from the "About Us" page, first via `aiohttp`, then falling back to ScrapingBee.
*   Extracts primary text content from the homepage (as the lowest priority fallback).
*   Combines text from discovered sources ("About Us" page, Wikipedia summary, LinkedIn snippet from Serper, homepage) to feed into the LLM.
*   Generates company descriptions using the OpenAI API, based on the configuration in `llm_config.yaml`.
*   Uses asynchronous processing for improved performance.
*   Saves results incrementally to CSV (one company at a time) to minimize data loss on failures.
*   Provides detailed process logging into unique files for each run.
*   Uses context files to refine searches and description generation.

## 2. Installation and Setup

### 2.1. Clone the Repository (if applicable)
```bash
git clone <repository_url>
cd <repository_directory>
```

### 2.2. Create and Activate a Virtual Environment (recommended)
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 2.3. Install Dependencies
All required libraries are listed in the `requirements.txt` file.
```bash
pip install -r requirements.txt
```
Key dependencies include: `pandas`, `openpyxl`, `aiohttp`, `beautifulsoup4`, `openai`, `scrapingbee`, `requests`, `PyYAML`, `python-dotenv`, `tldextract`, `wikipedia-api`.

### 2.4. Configure Environment Variables
The script requires API keys for external services. Create a `.env` file in the project's root directory. You can use `example.env` as a template (if provided) or simply add the following variables:

```env
SCRAPINGBEE_API_KEY="Your_ScrapingBee_Key"
OPENAI_API_KEY="Your_OpenAI_Key"
SERPER_API_KEY="Your_Serper.dev_Key"
```
**Note:** Ensure the `.env` file is added to your `.gitignore` to prevent accidentally publishing your keys.

### 2.5. LLM Configuration
Parameters for interacting with the OpenAI API (e.g., model, temperature, system prompt, user prompt) are configured in the `llm_config.yaml` file. The script expects this file in the root directory. An example structure:
```yaml
# llm_config.yaml
# --- Configuration for Description Generation ---
description_generation:
  model: "gpt-4o-mini" # Or another suitable model
  temperature: 0.2
  max_tokens: 400
  top_p: 0.9
  messages:
    - role: "system"
      content: >
        You are a meticulous AI analyst specializing in extracting and synthesizing company information strictly from provided text sources.
        The primary source text ('about_snippet') may contain combined information from the company's website (like an 'About Us' or homepage section, possibly marked with [From...]), its Wikipedia summary (marked with [From Wikipedia...]), and/or a snippet from LinkedIn search results (marked with [From LinkedIn...]). The text might be in any language.
        Your task is to generate a concise, fact-based company description *in English*, integrating information from all provided sources.

        Prioritize information from dedicated 'About Page' or 'Wikipedia' sections if available. Use 'LinkedIn Snippet' and 'Homepage' text to supplement if necessary.
        Focus on extracting and coherently presenting key details such as:
        - Legal name and headquarters location
        - Founding information (date, founders, if mentioned)
        - Core products, services, and technologies
        - Target markets or industries
        - Business model or key activities
        - Notable partnerships, clients, or projects mentioned
        - Stated company size or employee count (if available)
        - Any specific financial details mentioned (revenue, funding etc. - do not infer)

    - role: "user"
      content: >
        Generate a single-paragraph company description based *only* on the facts found within the following sources. Synthesize information from the different parts of the 'Extracted Text Snippet' if multiple sources are present (indicated by headers like [From...]).

        Sources:
        - Company Name: {company}
        - Official Site URL (if found): {website_url}
        - LinkedIn URL (if found): {linkedin_url}
        - Extracted Text Snippet (potentially combined from Website/Wikipedia/LinkedIn Snippet):
        ```text
        {about_snippet}
        ```
        - User Context (if provided): {context_text}

        Follow these rules strictly:
        1.  **Fact-Based Only:** Include only information explicitly stated or directly derivable from the provided sources, primarily the 'Extracted Text Snippet'. Do NOT add external knowledge, assumptions, or interpretations.
        2.  **Synthesize & Prioritize:** Combine information logically if multiple sources are present in the snippet. Give preference to facts from '[From About Page]' or '[From Wikipedia]' sections over '[From LinkedIn Serper Snippet]' and '[From Homepage]' text if available. Avoid redundancy.
        3.  **Neutral Tone:** Write in a neutral, objective, third-person narrative style using complete sentences.
        4.  **Conciseness:** Generate a dense paragraph. The length should reflect the amount of relevant information verified in the sources. Do not add filler content. If the snippet provides very little useful information, the description should be correspondingly brief or state that insufficient information was provided in the snippet.
        5.  **No Repetition:** Avoid repeating the same information using different phrasing.
        6.  **Formatting:** Output MUST be a single continuous paragraph. No markdown lists, headers, bullet points, tabs, or extra line breaks. Use digits for numbers (e.g., 10, 1995). Spell out acronyms on first use, followed by the acronym in parentheses, e.g., Saudi Broadcasting Authority (SBA).
        7.  **Handle Missing Data:** If specific information (like founding date, headquarters, etc.) is not present in the sources, simply omit it. Do not state that it's missing.
        8.  **Language:** The output description must be in English.
        9.  **Output:** Provide ONLY the generated paragraph.

        Description:

# --- Configuration for Homepage URL Selection ---
homepage_selection:
  model: "gpt-4o-mini" # Can use a faster model for this task
  temperature: 0.0
  max_tokens: 150 # Expect short response (URL or None)
  top_p: 1.0      # For determinism
  # Few-shot prompts are embedded directly in serper_client.py

# --- Configuration for "About Us" Link Selection ---
about_page_selection:
  model: "gpt-4o-mini"
  temperature: 0.0
  max_tokens: 150
  # Prompts are embedded directly in processing.py
```
Adapt `llm_config.yaml` to your needs.

## 3. Preparing Input Data

### 3.1. Company Files
*   Place files containing company names (one name per line, in the first column) into the `input/` folder.
*   Supported formats: `.xlsx`, `.xls`, `.csv`.
*   The script will automatically process all suitable files in this directory.

### 3.2. Context Files (optional)
*   For each input data file (e.g., `companies.xlsx`), you can create a corresponding text context file in the same `input/` folder, named `{base_filename}_context.txt` (e.g., `companies_context.txt`).
*   The content of this file will be used to refine search queries to Serper and will be passed to the LLM for more relevant description generation.
*   If a context file is not found, the script will prompt you to enter the context in the console. You can simply press Enter to skip.
*   If a context file exists, its content will be suggested as the default value.
*   The entered or confirmed context is saved/overwritten to the corresponding `_context.txt` file.

## 4. Running the Script
Ensure you have activated your virtual environment (if using one) and are in the project's root directory.
```bash
python -m src.pipeline
```
**Note:** Running via `python src/pipeline.py` might cause import errors due to relative paths (`from .config import ...`). Use the `-m` flag for correct module execution.

## 5. Script Workflow

For each company from the input file, the following steps are performed (asynchronously):

1.  **Load Context:** Reads or requests context for the current data file.
2.  **URL Search (via `serper_client.py`):**
    *   Queries are formulated for the Serper.dev API to find the main website (Homepage), LinkedIn company page (LI), and Wikipedia page (Wiki). Queries include the company name and words from the context file.
    *   Up to 30 search results are requested.
3.  **URL Selection:**
    *   **Homepage:** A filtered list of candidates (excluding social media, wikis, etc.) is passed to an LLM (OpenAI) with a few-shot prompt to select the most relevant homepage. A "second attempt" mechanism with a stricter prompt is used if the first fails. The found URL is cleaned to its base (scheme + netloc) for CSV output.
    *   **LinkedIn:** The best `/company/` URL is found using a scoring system (name match, title presence). The associated `snippet` from Serper is saved. The found URL is cleaned (trailing `/about/` removed) for CSV output.
    *   **Wikipedia:** The first `wikipedia.org` link found in the Serper results is selected.
4.  **Scrape Homepage (via `scrapingbee_client.py`):**
    *   HTML content of the found homepage is downloaded (using the *full* URL found in step 3). An async wrapper for ScrapingBee is used.
5.  **Find and Scrape "About Us" Page (via `processing.py`):**
    *   If homepage HTML was obtained, the `find_and_scrape_about_page_async` function analyzes it:
        *   Finds internal links on the same domain.
        *   Passes a filtered list of candidates (link + link text) to an LLM (OpenAI) to select the most likely "About Us" link.
        *   If the LLM fails, falls back to keyword search (`about_section_keywords` in `processing.py`).
        *   Attempts to download the selected "About Us" page first with `aiohttp`, then falls back to `ScrapingBee`.
        *   Extracts text from the downloaded page using `extract_text_for_description`.
6.  **Fetch Wikipedia Summary (via `processing.py`):**
    *   If a Wikipedia URL was found, `get_wikipedia_summary_async` extracts the page title from the URL and uses the `wikipedia-api` library to get the article summary.
7.  **Extract Homepage Text & Validate (via `processing.py`):**
    *   If no text was found on an "About Us" page, `extract_text_for_description` attempts to extract text from the homepage HTML.
    *   If text is extracted from the homepage, `validate_page` checks its relevance (by presence of company name in title, domain, meta tags, content).
8.  **Combine Texts (in `pipeline.py`):**
    *   The final text (`text_src`) for the LLM is assembled in the following priority order:
        1.  Text from "About Us" page (if found).
        2.  Wikipedia summary (if found).
        3.  LinkedIn snippet from Serper (if found).
        4.  Text from Homepage (only if "About Us" and Wikipedia text were not found, and the homepage was validated).
    *   Each source is marked with a header (e.g., `[From Wikipedia Summary]:`).
9.  **Generate Description (via `openai_client.py`):**
    *   The combined text (`text_src`), company name, found URLs, and context are passed to the OpenAI model (configured in `llm_config.yaml`) to generate the final description.
    *   A check is applied to discard unreasonably long LLM responses relative to the input to prevent hallucinations.
10. **Save Result (in `data_io.py`):**
    *   Data for the processed company (including cleaned Homepage and LinkedIn URLs) is immediately appended to the corresponding CSV file using `save_results_csv`.

## 6. Output Data

### 6.1. CSV Files with Results
*   For each processed input file, a CSV file is created in the `output/final_outputs/` folder.
*   The filename is formatted as: `{input_filename_without_extension}_output_{YYYYMMDD_HHMMSS}.csv`, where the timestamp corresponds to the script execution time.
*   The file contains columns: `name`, `homepage` (base URL), `linkedin` (base URL), `description`.
*   Data is appended to the CSV file for each company as it is processed.

### 6.2. Log Files
*   Logs are saved in the `output/logs/` folder.
*   Two unique log files with a timestamp in their names are created for each run:
    *   `pipeline_run_{YYYYMMDD_HHMMSS}.log`: Main log for the entire pipeline operation.
    *   `scoring_details_{YYYYMMDD_HHMMSS}.log`: Detailed log of the URL selection process (useful for debugging link selection logic).
*   Log files are created anew for each run (`mode='w'`).

## 7. Project Structure

The project has the following structure (main components):
*   `src/`:
    *   `pipeline.py`: Orchestrates the entire process, handles file and individual company processing.
    *   `config.py`: Loads API keys from `.env` and LLM configuration from `llm_config.yaml`.
    *   `data_io.py`: Functions for loading input data (Excel/CSV), loading/saving context files, and saving results to CSV.
    *   `processing.py`: Functions for page validation, text extraction, finding/scraping "About Us" page, fetching Wikipedia summary.
    *   `external_apis/`: Modules for interacting with external APIs:
        *   `serper_client.py`: URL search via Serper.dev, logic for Homepage/LinkedIn/Wikipedia URL selection.
        *   `scrapingbee_client.py`: Page scraping via ScrapingBee (async wrapper).
        *   `openai_client.py`: Description generation via OpenAI.
*   `input/`: Folder for input files (`.csv`, `.xlsx`) and context files (`_context.txt`).
*   `output/`:
    *   `final_outputs/`: Folder for the resulting CSV files.
    *   `logs/`: Folder for log files.
*   `requirements.txt`: List of Python dependencies.
*   `.env`: File for storing API keys (needs to be created).
*   `llm_config.yaml`: Configuration file for OpenAI models.
*   `README.md`: This documentation file.

## 8. Potential Issues and Debugging

*   **Missing API Keys:** Ensure the `.env` file exists and contains correct keys.
*   **Dependency Installation Errors:** Check your Python and pip versions. Try reinstalling problematic packages.
*   **Site/API Access Problems:** May be caused by network restrictions, site blocks, or API rate limits. Check error messages in the logs.
*   **Suboptimal URL Selection or Description Generation:**
    *   Modify prompts or model parameters in `llm_config.yaml`.
    *   Refine context in `_context.txt` files.
*   **Long Execution Time:** For a large number of companies, the process can take a significant amount of time despite asynchronicity.
*   **`TypeError: ... missing 1 required positional argument: 'context_text'`:** Ensure you have the latest code version where this was fixed in the `generate_description_openai_async` call in `src/pipeline.py`.
