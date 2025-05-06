# Company Data Enrichment Pipeline

## Overview

This Python script automates the process of enriching a list of company names provided in an Excel or CSV file. For each company, it performs the following steps asynchronously:

1.  **Find URLs:** Uses the Serper.dev Google Search API to find the likely official website homepage and LinkedIn company profile URL. User-provided context is used to refine searches.
2.  **Scrape Pages:** Uses the ScrapingBee API to scrape the HTML content of the found URLs. It attempts a simple fetch first and falls back to JavaScript rendering if necessary.
3.  **Extract Content:** Parses the scraped HTML to find relevant text snippets (meta description, first paragraph, or specific sections like "About").
4.  **Generate LLM Output:** Sends the company name, found URLs, extracted text, and user-provided context to the OpenAI API (using a configurable model like GPT-4o Mini) based on a flexible configuration file (`llm_config.yaml`). It can be configured to return either a structured JSON object or a text description.
5.  **Save Results:** Saves the enriched data (including homepage URL, LinkedIn URL, and the LLM output) into a unique CSV file in the `output/final_outputs/` directory for each input file processed. A consolidated JSON summary is also printed to the console upon completion.

## Features

*   Handles input company lists from both Excel (`.xlsx`, `.xls`) and CSV (`.csv`) files located in the `input/` directory.
*   Reads company names from the **first column** of the input file, regardless of the header name.
*   Uses **Serper.dev** for robust Google Search results.
*   Uses **ScrapingBee** with a simple-fetch/JS-render fallback mechanism for reliable web scraping.
*   Utilizes **OpenAI API** for data extraction or description generation.
*   **Asynchronous Processing:** Leverages `asyncio` and `aiohttp` for efficient, non-blocking I/O operations (Serper search, ScrapingBee scraping, OpenAI calls), significantly speeding up processing for large lists.
*   **Context-Aware Processing:** Prompts the user to provide context (industry, region, source, etc.) for each input file if a corresponding `_context.txt` file is missing. This context is used to refine searches and inform the LLM.
*   **Flexible LLM Configuration:** Uses a single `llm_config.yaml` file to define the OpenAI model, API parameters (temperature, max_tokens, etc.), and the structure/content of messages sent to the API, including support for **JSON Mode**.
*   **Structured or Text Output:** Can be configured via `llm_config.yaml` to request structured JSON output or a plain text description from the LLM. Output CSV columns adapt accordingly.
*   **Unique Output Files:** Automatically generates unique output CSV filenames (e.g., `data_output_1.csv`) in `output/final_outputs/` to prevent overwriting previous results.

## Prerequisites

*   Python 3.8+
*   `pip` (Python package installer)

## Setup

1.  **Clone Repository (Optional):**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```
    Or ensure you have the project files (`main.py`, `requirements.txt`, etc.) in a directory.

2.  **Create Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    ```
    Activate the environment:
    *   Windows (cmd.exe): `venv\Scripts\activate.bat`
    *   Windows (PowerShell): `venv\Scripts\Activate.ps1`
    *   Linux/macOS: `source venv/bin/activate`
    *(You should see `(venv)` preceding your command prompt)*

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create `.env` File:**
    Create a file named `.env` in the project's root directory. Add your API keys like this:
    ```dotenv
    SERPER_API_KEY=your_serper_dev_api_key
    SCRAPINGBEE_API_KEY=your_scrapingbee_api_key
    OPENAI_API_KEY=your_openai_api_key
    ```
    *   Get Serper API key from [serper.dev](https://serper.dev/).
    *   Get ScrapingBee API key from [scrapingbee.com](https://www.scrapingbee.com/).
    *   Get OpenAI API key from [platform.openai.com](https://platform.openai.com/).

## Configuration

1.  **Input Files (`input/` directory):**
    *   Place your data files (`.xlsx`, `.xls`, or `.csv`) containing company names in the `input/` directory.
    *   The script expects company names to be in the **first column**. The header name of this column does not matter.

2.  **Context Files (`input/` directory):**
    *   **Optional but Recommended:** For each data file (e.g., `my_companies.xlsx`), you can create a corresponding text file named `my_companies_context.txt` in the *same* `input/` directory.
    *   **Purpose:** This file provides context about the list (e.g., "Source: Web Summit 2024 Attendees", "Industry Focus: European Fintech Startups", "Region: DACH", "Keywords: AI, ML").
    *   **Interaction:** If the script does not find a `_context.txt` file for a data file, it will **prompt you** in the console to enter the context interactively. The entered text will then be saved to the corresponding `_context.txt` file for future runs. If you press Enter without typing, processing continues without context for that file.

3.  **LLM Configuration (`llm_config.yaml`):**
    *   This single YAML file controls the interaction with the OpenAI API.
    *   **`model` (Required):** The name of the OpenAI model to use (e.g., "gpt-4o-mini", "gpt-3.5-turbo").
    *   **`messages` (Required):** A list defining the sequence and content of messages sent to the API. Each item must be a dictionary with `role` (`system`, `user`, `assistant`) and `content` (string).
        *   **Placeholders:** You can use the following placeholders within the `content` strings. They will be automatically replaced by the script:
            *   `{company}`: The company name being processed.
            *   `{website_url}`: The found homepage URL (root domain) or "N/A".
            *   `{linkedin_url}`: The found LinkedIn URL or "N/A".
            *   `{about_snippet}`: The text extracted from the scraped pages.
            *   `{user_provided_context}`: The text loaded from the `_context.txt` file (or "Not provided").
    *   **Other OpenAI Parameters:** Any other valid key-value pairs recognized by the OpenAI Chat Completion API (e.g., `temperature`, `max_tokens`, `top_p`, `response_format`) can be added here and will be passed directly to the API call.
    *   **JSON Mode Example:** To request structured JSON output, add:
        ```yaml
        response_format: { "type": "json_object" } 
        ```
        *(Ensure your `messages` instruct the model to produce JSON with the desired schema when using this mode.)*

## Usage

1.  **Activate Virtual Environment** (if you created one):
    ```bash
    # Example for PowerShell:
    .\venv\Scripts\Activate.ps1 
    ```
2.  **Run the script:**
    ```bash
    python main.py
    ```
3.  **Provide Context (if prompted):** If context files (`_context.txt`) are missing for any input data files, the script will ask you to enter context information in the terminal. Type the relevant details and press Enter, or just press Enter to skip context for that file.
4.  **Monitor Output:**
    *   The script will print progress messages to the console, including which file and company is being processed, results of URL searches, scraping attempts, validation, and LLM generation status.
    *   Errors encountered during processing (API errors, timeouts, etc.) will also be logged to the console.
5.  **Check Results:**
    *   For each processed input file (`data.xlsx`), a corresponding output CSV file (e.g., `data_output.csv`, `data_output_1.csv`, etc.) will be created in the `output/final_outputs/` directory.
    *   **Output Columns:**
        *   Standard columns: `name`, `homepage`, `linkedin`.
        *   If JSON mode was used successfully, additional columns (`llm_key1`, `llm_key2`, ...) based on the keys in the JSON returned by the LLM will be present. The default `description` column will be omitted in this case.
        *   If text output was generated (or errors occurred), the result will be in the `description` column.
    *   At the very end of the script run, a consolidated JSON summary of all successfully processed company results from all files will be printed to the console.

## Troubleshooting

*   **`ModuleNotFoundError: No module named '...'`:** Ensure your virtual environment is activated *before* running `pip install -r requirements.txt` and `python main.py`. Verify the required library is listed in `requirements.txt`.
*   **`Import "..." could not be resolved` (in IDE):** This is an IDE configuration issue. Make sure your IDE's Python interpreter is set to the one inside your `venv` folder. Restart the IDE after selecting the interpreter.
*   **API Key Errors (Serper, ScrapingBee, OpenAI):** Double-check the keys in your `.env` file are correct, correspond to the right service, and haven't expired or hit usage limits. Check the respective service dashboards.
*   **Context File Prompt Keeps Appearing:** Ensure the `_context.txt` files are named correctly (matching the data file base name) and are placed in the `input/` directory. Make sure they are not empty if you want them to be used silently.
*   **LLM Errors / Bad Output:**
    *   Check `llm_config.yaml` syntax carefully.
    *   Verify the `model` name is correct and supported.
    *   Ensure all placeholders used in the `messages` content (`{company}`, `{about_snippet}`, etc.) are correctly spelled.
    *   Adjust `temperature`, `max_tokens`, and other parameters.
    *   Refine the prompts in the `messages` section for better clarity and instruction.
    *   If using JSON mode, ensure your prompt clearly requests JSON output and specifies the desired schema. Check the console for JSON parsing errors if the output isn't structured as expected.
*   **Scraping Failures (`Scrape task ... failed`):** Some websites might be heavily protected or load content in unusual ways. The script attempts JS rendering, but complex sites might still fail. Manual review might be needed for these URLs. Consider adding `premium_proxy=True` to ScrapingBee parameters in `scrape_page_data` for difficult sites (increases cost).
*   **No Output Files Generated:** Check console logs for errors during file loading (`load_and_prepare_company_names`) or if no supported files were found in the `input` directory. Ensure the first column of your input files contains valid company names. 