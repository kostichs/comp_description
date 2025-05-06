# Company Data Enrichment Pipeline

## Overview

This Python script automates the process of enriching a list of company names provided in an Excel or CSV file. For each company, it performs the following steps asynchronously:

1.  **Find URLs:** Uses the Serper.dev Google Search API to find the likely official website homepage and LinkedIn company profile URL. User-provided context is used to refine searches.
2.  **Scrape Pages:** Uses the ScrapingBee API to scrape the HTML content of the found URLs. It attempts a simple fetch first and falls back to JavaScript rendering if necessary.
3.  **Extract Content:** Parses the scraped HTML to find relevant text snippets (meta description, first paragraph, or specific sections like "About").
4.  **Generate LLM Output:** Sends the company name, found URLs, extracted text, and user-provided context to the OpenAI API (using a configurable model like GPT-4o Mini) based on a flexible configuration file (`llm_config.yaml`). It can be configured to return either a structured JSON object or a text description.
5.  **Save Results:** Saves the enriched data (including homepage URL, LinkedIn URL, and the LLM output) into a unique CSV file in the `output/final_outputs/` directory for each input file processed. A consolidated JSON summary is also printed to the console upon completion.

**Code Structure:** The project utilizes a modular structure with core logic located within the `src/` directory for better organization and maintainability.

## Features

*   Handles input from Excel (`.xlsx`, `.xls`) and CSV (`.csv`) files in `input/`.
*   Reads company names from the **first column** of the input file, regardless of the header name.
*   Uses **Serper.dev** for robust Google Search results.
*   Uses **ScrapingBee** with a simple-fetch/JS-render fallback mechanism for reliable web scraping.
*   Utilizes **OpenAI API** for data extraction or description generation.
*   **Asynchronous Processing:** Leverages `asyncio` and `aiohttp` for efficient, non-blocking I/O operations (Serper search, ScrapingBee scraping, OpenAI calls), significantly speeding up processing for large lists.
*   **Context-Aware Processing:** Prompts the user to provide context (industry, region, source, etc.) for each input file if a corresponding `_context.txt` file is missing. This context is used to refine searches and inform the LLM.
*   **Flexible LLM Configuration:** Uses a single `llm_config.yaml` file to define the OpenAI model, API parameters (temperature, max_tokens, etc.), and the structure/content of messages sent to the API, including support for **JSON Mode**.
*   **Structured or Text Output:** Can be configured via `llm_config.yaml` to request structured JSON output or a plain text description from the LLM. Output CSV columns adapt accordingly.
*   **Unique Output Files:** Automatically generates unique output CSV filenames (e.g., `data_output_1.csv`) in `output/final_outputs/` to prevent overwriting previous results.
*   **Modular Codebase** (logic primarily in `src/` package).

## Prerequisites

*   Python 3.8+
*   `pip` (Python package installer)

## Setup

1.  **Clone/Download Project:** Obtain the project files.
2.  **Navigate to Root Directory:** `cd <project_directory>` (the one containing `main.py` and `src/`).
3.  **Create Virtual Environment:**
    ```bash
    python -m venv venv
    ```
    Activate it (e.g., `.\venv\Scripts\Activate.ps1` on PowerShell).
4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
5.  **Create `.env` File:** In the root directory, create `.env` and add:
    ```dotenv
    SERPER_API_KEY=your_serper_dev_key
    SCRAPINGBEE_API_KEY=your_scrapingbee_key
    OPENAI_API_KEY=your_openai_key
    ```

## Configuration

1.  **Input Files (`input/`):** Place data files (`.xlsx`, `.xls`, `.csv`) here. Company names must be in the first column.
2.  **Context Files (`input/`):** (Optional) Create `filename_context.txt` for each data file to provide context (industry, region etc.). If missing, you will be prompted.
3.  **LLM Configuration (`llm_config.yaml`):**
    *   Defines **all** OpenAI API parameters and the `messages` structure.
    *   **`model` (Required):** e.g., "gpt-4o-mini".
    *   **`messages` (Required):** List of `{"role": ..., "content": ...}` dictionaries. Use placeholders like `{company}`, `{about_snippet}`, `{user_provided_context}` etc. within `content`.
    *   **Other Params:** Add `temperature`, `max_tokens`, `response_format: { "type": "json_object" }`, etc. directly in this file.

## Usage

1.  **Activate Virtual Environment.**
2.  **Run from Project Root:**
    ```bash
    python main.py
    ```
3.  **Provide Context:** Enter context when prompted if `_context.txt` files are missing.
4.  **Monitor Output:** View progress and errors in the console.
5.  **Check Results:**
    *   Output CSV files appear in `output/final_outputs/` (e.g., `data_output.csv`, `data_output_1.csv`, etc.).
    *   **Output Columns:** The CSV columns will typically be ordered as follows:
        *   `name`
        *   `homepage`
        *   `linkedin`
        *   `description` (Contains text output from LLM, error messages, or status like "Manual check required"). This column might be omitted if JSON mode successfully returned structured data.
        *   If JSON mode was used successfully, additional columns prefixed with `llm_` (e.g., `llm_legal_name`, `llm_headquarters_location`, etc.) based on the keys returned by the LLM will follow, sorted alphabetically.
    *   A final JSON summary of all successful results is printed to the console.

## Troubleshooting

*   **`ModuleNotFoundError` / `ImportError: cannot import name '...' from 'src...'`:** Ensure venv is active AND you are running `python main.py` from the **project root directory** (the one containing `main.py` and `src/`).
*   **`Import "..." could not be resolved` (IDE):** Configure your IDE's Python interpreter to use the one from `./venv/Scripts/python.exe`.
*   **API Key Errors:** Double-check `.env` file contents and API key status on service dashboards.
*   **Context Prompt Issues:** Verify `_context.txt` file names/locations. Ensure they aren't empty if you want to skip the prompt.
*   **LLM Errors:** Check `llm_config.yaml` syntax, `model` name, placeholder spellings in `messages`. Adjust API parameters. If using JSON mode, ensure the prompt requests it clearly.
*   **Scraping Failures:** Some sites are difficult. Consider `premium_proxy=True` in `src/external_apis/scrapingbee_client.py` (increases cost).
*   **No Output:** Check logs for file loading errors. Ensure input files have data in the first column. 