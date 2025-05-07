# Python Company Information Scraper & LLM Description Generator

## 1. Project Overview

This project is a Python script designed to automatically gather information about companies, including their websites and LinkedIn profiles, scrape these pages, extract relevant text content, and then generate concise descriptions using OpenAI models.

**Key Features:**
*   Processes a list of companies from `.xlsx` or `.csv` files.
*   Uses Serper.dev to find company URLs (main website and LinkedIn).
*   Employs an advanced two-pass ranking system for found URLs to select the most relevant ones.
*   Scrapes web pages using ScrapingBee (with JavaScript rendering support).
*   Extracts primary text content from pages.
*   Generates company descriptions using the OpenAI API, flexibly configured via a YAML file.
*   Utilizes asynchronous processing for improved performance.
*   Incrementally saves results to CSV for each processed company to minimize data loss in case of failures.
*   Provides detailed logging of the process into unique files for each run.
*   Uses context files to refine searches and description generation.

## Quick Start Guide

1.  **Prepare Input Data:**
    *   Place your data file (e.g., `companies.xlsx` or `companies.csv`) containing company names (in the first column) into the `input/` folder.
2.  **Set API Keys:**
    *   Create a `.env` file in the project root and add your API keys for `SERPER_API_KEY`, `SCRAPINGBEE_API_KEY`, and `OPENAI_API_KEY`. (See section 2.4 for more details if needed).
3.  **Install Dependencies (if first time):**
    *   Ensure you have Python and pip installed.
    *   Open your terminal, navigate to the project root.
    *   It's recommended to use a virtual environment (see section 2.2).
    *   Run: `pip install -r requirements.txt`
4.  **Run the Application:**
    *   Open your terminal, navigate to the project root directory.
    *   Activate your virtual environment if you created one.
    *   Execute: `python main.py`
5.  **Provide Context (when prompted):**
    *   For each input file, the script will ask for additional clarifying details (e.g., "Location: Berlin", "Industry: Fintech", "Source Event: Tech Conference 2024"). Enter these as brief notes or press Enter to use existing context (if available from a `_context.txt` file) or to skip providing context for that file.
6.  **Check Results:**
    *   Output CSV files (e.g., `companies_output_{timestamp}.csv`) will be saved in the `output/final_outputs/` folder.
7.  **Review Logs (optional, for troubleshooting):**
    *   Detailed logs for each run are stored in the `output/logs/` folder (e.g., `pipeline_run_{timestamp}.log` and `scoring_details_{timestamp}.log`).

For more detailed setup and configuration, please refer to the sections below.

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
Key dependencies include: `pandas`, `openpyxl`, `aiohttp`, `beautifulsoup4`, `openai`, `scrapingbee`, `requests` (for direct Serper calls, if not using a dedicated Serper library), `PyYAML`, `python-dotenv`, `tldextract`, `scikit-learn` (for cosine similarity of embeddings).

### 2.4. Configure Environment Variables
The script requires API keys for external services. Create a `.env` file in the project's root directory. You can use `example.env` as a template (if provided) or simply add the following variables:

```env
SCRAPINGBEE_API_KEY="Your_ScrapingBee_Key"
OPENAI_API_KEY="Your_OpenAI_Key"
SERPER_API_KEY="Your_Serper.dev_Key"
```
**Note:** Ensure the `.env` file is added to your `.gitignore` to prevent accidentally publishing your keys. If an `.env.example` file is missing, create `.env` and populate it with the necessary keys.

### 2.5. LLM Configuration
Parameters for interacting with the OpenAI API (e.g., model, temperature, system prompt, user prompt) are configured in the `llm_config.yaml` file. The script expects this file in the root directory. An example structure might include:
```yaml
model: "gpt-4o-mini"
temperature: 0.4
max_tokens: 350
top_p: 0.9
# expected_json_keys: ["summary", "industry", "location"] # If type is json_object, you can specify expected keys

messages:
  - role: "system"
    content: "You are an AI assistant that generates company descriptions based on provided text."
  - role: "user"
    content: "Based on the following text from the company [COMPANY_NAME] (Website: [WEBSITE_URL], LinkedIn: [LINKEDIN_URL]), please prepare a description.\n\nContext for search/company (if any): [CONTEXT]\n\nText for analysis:\n{text_content}\n\nProvide the description in JSON format (if specified in response_format) or as text."
```
Adapt `llm_config.yaml` to your needs. The `expected_json_keys` field can be used to automatically form CSV headers if a JSON response from the LLM is chosen.

## 3. Preparing Input Data

### 3.1. Company Files
*   Place files containing company names (one name per line, in the first column) in the `input/` folder.
*   Supported formats: `.xlsx`, `.xls`, `.csv`.
*   The script will automatically process all suitable files in this directory.

### 3.2. Context Files (optional)
*   For each input data file (e.g., `companies.xlsx`), you can create a corresponding text context file in the same `input/` folder, named `{base_filename}_context.txt` (e.g., `companies_context.txt`).
*   The content of this file will be used to refine search queries to Serper and will be passed to the LLM for more relevant description generation.
*   If a context file for a data file is not found, the script will prompt you to enter the context in the console. You can simply press Enter to skip.
*   If a context file exists, its content will be suggested as the default value.
*   The entered or confirmed context is saved/overwritten to the corresponding `_context.txt` file.

## 4. Running the Script
Ensure you have activated your virtual environment (if using one) and are in the project's root directory.
```bash
python main.py
```

## 5. Script Workflow

For each company from the input file, the following steps are performed:

1.  **Load Context:** The context for the current data file is read or requested.
2.  **URL Search (via `serper_client.py`):**
    *   Search queries are formulated for the Serper.dev API to find the main website (HP) and the LinkedIn company page (LI). Queries include the company name and words from the context file.
    *   Up to 20 search results are requested per query.
3.  **URL Ranking and Selection (Two-Pass System in `serper_client.py`'s `rank_serper_results_async`):**
    *   **Company Name Preparation:** The input company name is normalized by `_prepare_company_name_for_strict_domain_check` (lowercase, remove spaces/punctuation, remove leading "www") for matching against domain parts.
    *   **Pass 1 (Strict Selection):** Iterates through all search results.
        *   **For Homepage (HP):** A URL is selected if it meets ALL the following criteria:
            1.  The `domain` part of the URL (e.g., "companyname" from `www.companyname.com`) exactly matches the prepared company name.
            2.  The `subdomain` part is empty or "www" (filters out URLs like `jobs.companyname.com`).
            3.  The Top-Level Domain (TLD, e.g., "com", "uk") is in the `PREFERRED_TLDS` list (defined in `serper_client.py`).
            4.  The URL path is a root path (e.g., `/` or empty).
        *   **For LinkedIn (LI) (if `prefer_linkedin_company` is true):** Checks for valid LinkedIn company URL format and uses a basic scoring based on slug matching against `normalize_company_name_for_domain_match` and company name in title. Selects if a threshold is met.
        *   If a URL is found in Pass 1, it's returned immediately.
    *   **Pass 2 (Flexible Scoring):** If Pass 1 yields no result, this pass is executed over all search results again.
        *   Applies a weighted scoring system considering: partial domain matches, company name in title/snippet, presence of "official"/"homepage" keywords, penalties for `NEGATIVE_KEYWORDS_FOR_RANKING`, TLD relevance (including context TLD), context keyword presence in title/snippet, and cosine similarity of OpenAI embeddings (company name vs. title+snippet, if embeddings are enabled and available).
        *   The first URL exceeding a dynamic score threshold (based on TLD preference) is selected.
    *   Blacklisted domains (defined in `BLACKLISTED_DOMAINS` in `serper_client.py`) are skipped in both passes.
4.  **Page Scraping (via `scrapingbee_client.py`):**
    *   The selected URLs (HP and/or LI) are scraped using ScrapingBee. An asynchronous approach is used.
5.  **Canonical URL Extraction (in `processing.py`):** An attempt is made to extract a definitive canonical URL from the main page's HTML (meta tags `og:url`, `canonical`).
6.  **Page Validation (in `processing.py`):** The relevance of scraped pages is checked (e.g., by matching the company name in the page `title`).
7.  **Text Extraction (in `processing.py`):** Main text content (meta descriptions, `<p>` tags, "About Us" sections, etc.) is extracted from the validated page (HP preferred, then LI).
8.  **Description Generation (via `openai_client.py`):**
    *   The extracted text, company name, URLs, and context are passed to the OpenAI model (configured in `llm_config.yaml`).
    *   The generated description (text or JSON) is added to the results.
9.  **Result Saving (in `data_io.py`):** Data for the processed company is immediately appended to the corresponding CSV file using `save_results_csv`.

## 6. Output Data

### 6.1. CSV Files with Results
*   For each processed input file, a CSV file is created in the `output/final_outputs/` folder.
*   The filename is formatted as: `{input_filename_without_extension}_output_{YYYYMMDD_HHMMSS}.csv`, where the timestamp corresponds to the script execution time. This allows easy correlation of results with logs.
*   The file contains columns: `name`, `homepage`, `linkedin`, `description`, followed by any fields returned by the LLM (if the response is JSON, e.g., `llm_summary`, `llm_industry`, etc.). The order of the first four columns is fixed.
*   Data is appended to the CSV file for each company as it is processed, preventing data loss in case of crashes.

### 6.2. Log Files
*   Logs are saved in the `output/logs/` folder.
*   Two unique log files with a timestamp in their names are created for each run:
    *   `pipeline_run_{YYYYMMDD_HHMMSS}.log`: Main log for the entire pipeline operation.
    *   `scoring_details_{YYYYMMDD_HHMMSS}.log`: Detailed log of the URL ranking process (useful for debugging link selection logic).
*   Log files are created anew for each run (`mode='w'`).

## 7. Customizing URL Selection Logic

The core logic for URL discovery and ranking resides in `src/external_apis/serper_client.py`.

*   **Key Function:** `rank_serper_results_async` implements the two-pass system described in the "Script Workflow" section.
*   **Primary Customization Points:**
    *   `PREFERRED_TLDS`: List of preferred Top-Level Domains for the strict (Pass 1) and flexible (Pass 2) checks.
    *   `BLACKLISTED_DOMAINS`: List of domains to always ignore.
    *   `NEGATIVE_KEYWORDS_FOR_RANKING`: List of keywords that reduce a URL's score in the flexible pass (Pass 2) if found in title, link, or snippet.
    *   **Pass 1 (Strict) Criteria:** The conditions for domain name matching, subdomain allowance, TLD, and root path are hardcoded in the first part of `rank_serper_results_async`. Modifying these requires direct code changes.
    *   **Pass 2 (Flexible) Scoring Weights & Thresholds:** The second part of `rank_serper_results_async` contains various scoring increments/decrements (e.g., `score += 15` for exact domain match, `score -= 3` for negative keyword). These numeric values, as well as `old_score_threshold` and `non_preferred_tld_score_threshold`, can be adjusted to tune the flexibility of the second pass.
    *   `normalize_company_name_for_domain_match` and `_prepare_company_name_for_strict_domain_check`: These functions handle company name normalization before matching. Changes here will affect how names are compared to domain parts.
*   **Debugging Ranking:** The most effective way to understand and tune the ranking is to:
    1.  Examine the `output/logs/scoring_details_{timestamp}.log` file. It logs the reasons why candidates pass or fail the strict (L1) checks and shows the detailed score breakdown for candidates in the flexible (L2) pass.
    2.  Use specific company names in your input that are problematic.
    3.  Iteratively adjust the lists (`PREFERRED_TLDS`, etc.) and scoring weights/thresholds in `serper_client.py` based on the log analysis until the desired behavior is achieved.

## 8. Modular Structure

The project has the following structure (main components):
*   `main.py`: Entry point, launches the main pipeline.
*   `src/`:
    *   `pipeline.py`: Orchestrates the entire process, handles file and individual company processing.
    *   `config.py`: Loads API keys from `.env` and LLM configuration from `llm_config.yaml`. Also contains the `SPECIAL_COMPANY_HANDLING` dictionary.
    *   `data_io.py`: Functions for loading input data (Excel/CSV), loading/saving context files, and saving results to CSV.
    *   `processing.py`: Functions for page validation, text extraction from pages, and canonical URL extraction.
    *   `external_apis/`: Modules for interacting with external APIs:
        *   `serper_client.py`: URL search via Serper.dev, link ranking logic.
        *   `scrapingbee_client.py`: Page scraping via ScrapingBee.
        *   `openai_client.py`: Description generation and embedding retrieval via OpenAI.

## 9. Potential Issues and Debugging

*   **Missing API Keys:** Ensure the `.env` file exists and contains correct keys.
*   **Dependency Installation Errors:** Check your Python and pip versions. Try reinstalling problematic packages.
*   **Site/API Access Problems:** May be caused by network restrictions, site blocks, or API rate limits. Check error messages in the logs.
*   **Suboptimal URL Selection or Description Generation (beyond ranking logic):**
    *   Modify prompts or model parameters in `llm_config.yaml`.
    *   Refine context in `_context.txt` files.
*   **Long Execution Time:** For a large number of companies, the process can take a significant amount of time despite asynchronicity.

---

This `README.md` should provide a good overview of the project.

