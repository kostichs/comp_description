# Company Data Enrichment Pipeline

## Overview

This Python script automates the process of enriching a list of company names. For each company, it performs the following steps asynchronously:

1.  **Contextual URL Search:** Uses Serper.dev Google Search API with iterative queries (refined by user-provided context like industry/location) to find the most relevant official website and LinkedIn company profile URL. Results are ranked using a weighted scoring system that includes exact/partial name matches, domain relevance, keyword analysis, and semantic similarity via OpenAI embeddings.
2.  **Advanced Web Scraping:** Employs ScrapingBee API to fetch HTML content. It attempts a simple, fast request first, then falls back to full JavaScript rendering with a timeout if needed.
3.  **Multi-faceted Validation:** Validates scraped pages based on title, domain, HTML content signals (e.g., presence of "About Us", copyright notices, absence of e-commerce elements), and URL structure. An optional LLM-based check can further verify if the page is truly about the company.
4.  **Content Extraction:** Parses validated HTML to extract key text snippets (meta description, main paragraphs, "About" sections).
5.  **Configurable LLM Processing:** Sends company data, extracted text, and user context to an OpenAI model (e.g., GPT-4o Mini). The interaction is fully defined in `llm_config.yaml`, supporting custom messages, API parameters, and JSON Mode for structured output.
6.  **Organized Output:** Saves results to uniquely named CSV files (e.g., `InputFile_output_1.csv`) in `output/final_outputs/`. Columns include `name`, `homepage`, `linkedin`, and either a `description` or multiple `llm_*` fields if JSON output was generated. A consolidated JSON summary of all results is printed upon completion.

**Code Structure:** The project is modularized into the `src/` package, with distinct modules for configuration, data I/O, external API clients, processing logic, and the main pipeline orchestration, enhancing maintainability and readability.

## Features

*   Input from Excel (`.xlsx`, `.xls`) or CSV (`.csv`) files (company names in the first column).
*   Iterative, context-enhanced Serper.dev search with **advanced scoring and semantic ranking (embeddings)** for URL discovery.
*   Two-tier ScrapingBee scraping (simple fetch then JS render fallback).
*   Multi-level content validation (title, domain, HTML signals, URL structure, optional LLM check).
*   Asynchronous operations (`asyncio`, `aiohttp`) for high performance.
*   **Interactive Context Input:** Prompts user for context (industry, region, etc.) for each input file *on every run*, suggesting previously saved context. Context is saved to `_context.txt` files and used to refine searches and LLM prompts.
*   **Single, Flexible LLM Configuration (`llm_config.yaml`):** Defines OpenAI model, all API parameters (temperature, max_tokens, `response_format`), and the complete `messages` array (system, user, assistant roles) with placeholder support (`{company}`, `{website_url}`, `{linkedin_url}`, `{about_snippet}`, `{user_provided_context}`).
*   Adapts output CSV columns based on LLM output (single `description` or multiple `llm_` prefixed columns for JSON).
*   Prevents overwriting output files by generating unique names.

## Prerequisites

*   Python 3.8+
*   `pip`

## Setup

1.  **Clone/Download & Navigate:** Get project files and `cd` to the root directory (containing `main.py`).
2.  **Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    # Activate (e.g., Windows PowerShell: .\venv\Scripts\Activate.ps1)
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **`.env` File:** Create `.env` in the root with your API keys:
    ```dotenv
    SERPER_API_KEY=your_serper_dev_key
    SCRAPINGBEE_API_KEY=your_scrapingbee_key
    OPENAI_API_KEY=your_openai_key
    ```

## Configuration

1.  **Input Files (`input/` directory):**
    *   Place data files. Company names **must be in the first column**.
2.  **Context Files (`input/` directory):**
    *   For each data file (e.g., `my_data.xlsx`), the script looks for/creates `my_data_context.txt`.
    *   **On every run, for every data file, you will be prompted for context.**
    *   If a `_context.txt` exists, its content is shown as a default. Press Enter to use it, or type new/modified context.
    *   The context used is saved back to the file.
    *   Provide details like: `Industry: SaaS`, `Location: Berlin, Germany`, `Source Event: Cloud Expo 2024`, `Keywords: B2B, enterprise AI`.
3.  **LLM Configuration (`llm_config.yaml`):**
    *   This single YAML file **directly mirrors the OpenAI API request structure** where applicable.
    *   **Top-level keys** should be valid parameters for the OpenAI Chat Completions API (e.g., `model`, `temperature`, `max_tokens`, `top_p`, `response_format: { "type": "json_object" }`).
    *   **`model` (Required):** Specify the OpenAI model (e.g., "gpt-4o-mini").
    *   **`messages` (Required):** A list of message objects, each with `role` and `content`. Use placeholders:
        *   `{company}`: Company name.
        *   `{website_url}`: Found homepage (e.g., `https://example.com`).
        *   `{linkedin_url}`: Found LinkedIn URL.
        *   `{about_snippet}`: Text extracted from scraped pages.
        *   `{user_provided_context}`: Content from the corresponding `_context.txt` file.

## Usage

1.  **Activate Virtual Environment.**
2.  **Run from Project Root:**
    ```bash
    python main.py
    ```
3.  **Provide/Confirm Context:** For each input data file, you'll be prompted for context. Review/modify/enter as needed.
4.  **Monitor Console Output:** Track progress, URL findings, validation steps, LLM calls, and any errors.
5.  **Check Results:**
    *   Output CSVs are in `output/final_outputs/` with unique names.
    *   **Column Order:** `name`, `homepage`, `linkedin` first. Then `description` (for text LLM output or errors) OR `llm_*` columns (for structured JSON output from LLM, sorted alphabetically).
    *   A consolidated JSON of all successful results is printed at the end.

## Advanced: Calibrating Search Ranking

The relevance of found URLs is determined by a scoring system in `src/external_apis/serper_client.py` within the `rank_serper_results_async` function. To fine-tune this:
1.  **Enable Debug Logging:** In `rank_serper_results_async`, uncomment the `print` statement that shows the detailed `score_log` for each candidate URL.
2.  **Run with Test Cases:** Use input files with ambiguous or difficult company names.
3.  **Analyze Logs:** Observe how scores are calculated: which factors contribute positively or negatively.
4.  **Adjust Weights:** Modify the numerical values in `rank_serper_results_async` associated with:
    *   Domain matching (exact/partial).
    *   Name in title/snippet (exact/partial).
    *   Context keyword matches.
    *   Embedding similarity score multiplier.
    *   Penalties for negative keywords.
5.  **Adjust `score_threshold`:** This value in `rank_serper_results_async` determines the minimum score for a link to be considered valid.
6.  Iterate by re-running and re-analyzing until satisfied.

## Troubleshooting

*   **`ModuleNotFoundError` / `ImportError: ...src...`**: Ensure venv is active & you run `python main.py` from the project root.
*   **IDE Import Resolution Issues**: Set IDE's Python interpreter to `./venv/Scripts/python.exe`.
*   **API Key Errors**: Verify `.env` keys and service dashboards.
*   **Context Prompts**: Ensure `_context.txt` files are in `input/` if you want to pre-fill. They are always prompted for confirmation/update.
*   **LLM Issues**: Check `llm_config.yaml` (syntax, `model`, placeholders). For JSON mode, ensure your prompt clearly requests it.
*   **Scraping Failures**: Difficult sites may still fail. Consider `premium_proxy=True` in `ScrapingBeeClient` parameters within `src/external_apis/scrapingbee_client.py` (sync function `scrape_page_data`).
*   **No Output / Validation Failures**: Check logs for file loading errors, URL ranking scores, and validation steps. Ensure context is helpful. Company names should be in the first column of input files. 