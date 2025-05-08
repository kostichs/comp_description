# Company Information Scraper & LLM Description Generator

## 1. Project Overview

This project is a Python application designed to automatically gather information about companies (websites, LinkedIn, Wikipedia), extract relevant text, and generate concise descriptions using OpenAI models. It features a graphical user interface (GUI) built with Tkinter for managing processing sessions.

**Key Features:**
*   **Session Management:** Organizes work into sessions, each tied to an input file and context, with results and logs stored separately.
*   **GUI:** Provides a user-friendly interface for:
    *   Creating new processing sessions.
    *   Loading and browsing existing sessions.
    *   Selecting input files (`.xlsx`, `.csv`).
    *   Entering optional context to guide searches.
    *   Starting the processing pipeline.
    *   Viewing results directly in a table.
    *   Opening session folders.
*   **URL Discovery:** Uses Serper.dev API to find Homepage, LinkedIn, and Wikipedia URLs.
*   **Intelligent URL Selection:** Employs LLM (OpenAI) to select the most relevant Homepage and LinkedIn URLs from search results.
*   **Multi-Source Text Extraction:**
    *   Fetches Wikipedia summaries using `wikipedia-api`.
    *   Attempts to find and scrape "About Us" pages using `aiohttp` and ScrapingBee (fallback).
    *   Extracts text from homepages (lowest priority).
*   **Contextual Description Generation:** Combines text from all found sources (About page, Wikipedia, LinkedIn snippet, Homepage) and sends it to an OpenAI model (configured via `llm_config.yaml`) for description generation.
*   **Asynchronous Processing & Threading:** Uses `asyncio` for core processing and `threading` to keep the UI responsive during pipeline execution.
*   **Incremental Saving & Logging:** Results for each session are saved incrementally to a dedicated CSV file, and detailed logs are stored per session.

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
The script requires API keys for external services. Create a `.env` file in the project's root directory with the following variables:

```env
SCRAPINGBEE_API_KEY="Your_ScrapingBee_Key"
OPENAI_API_KEY="Your_OpenAI_Key"
SERPER_API_KEY="Your_Serper.dev_Key"
```
**Note:** Ensure the `.env` file is added to your `.gitignore`.

### 2.5. LLM Configuration (`llm_config.yaml`)
This file configures the OpenAI models used for description generation, homepage selection, and "About Us" link selection. Adjust models, temperature, and other parameters as needed. The prompts for selection tasks are embedded in the Python code (`serper_client.py`, `processing.py`), while the description generation prompt is loaded from this file.

## 3. Running the Application (GUI)

Ensure you have activated your virtual environment.
```bash
python app_ui.py 
```
This will launch the graphical user interface.

## 4. Using the GUI

1.  **Session Management:**
    *   **New Session:** Click "New Session" to start fresh. The input fields and results table will clear.
    *   **Load Session:** Select a previous session ID from the dropdown list. The input file, context (if saved), and results (if processing is complete) for that session will be loaded.
2.  **Input Configuration:**
    *   **Input File:** Click "Browse..." to select your `.xlsx` or `.csv` file containing company names (required only for *new* sessions).
    *   **Context:** Enter any relevant context (industry, location, etc.) in the text box. This helps refine searches and descriptions.
3.  **Start Processing:**
    *   Click "Start Processing".
    *   The UI will become unresponsive while initializing, then the status bar will show "Processing...". Buttons will be disabled.
    *   Processing runs in the background.
4.  **View Results:**
    *   When processing for the *currently selected* session finishes, the results table will automatically populate.
    *   For previously completed sessions, selecting the session from the dropdown will load its results into the table.
5.  **Open Session Folder:**
    *   Click "Open Session Folder" to open the directory containing the input copy (optional), context file, results CSV, and log files for the currently selected session.

## 5. Session Data Structure

All session-related data is stored within the `output/sessions/` directory. Each sub-directory corresponds to a unique session ID (e.g., `20250509_101500_input_test1`):

*   `output/sessions/{session_id}/results.csv`: The incrementally saved CSV results for the session.
*   `output/sessions/{session_id}/pipeline.log`: Main pipeline log for the session.
*   `output/sessions/{session_id}/scoring.log`: Detailed URL scoring log for the session.
*   `output/sessions/{session_id}/context_used.txt`: The context used for this session.
*   `(Optional) output/sessions/{session_id}/input_used.*`: A copy of the input file used.

Session metadata (linking IDs to file paths, status, etc.) is stored in `sessions_metadata.json` in the project root.

## 6. Script Workflow (Detailed)

*(The core logic described in the previous README version remains largely the same, but is now orchestrated by `app_ui.py` calling `run_pipeline_for_file` within `src/pipeline.py` for a specific session).* 

Key steps for each company within a session:

1.  **URL Search:** Serper API finds Homepage, LinkedIn, Wikipedia URLs based on company name + context.
2.  **URL Selection:** LLM selects best Homepage. Custom scoring (soon to be LLM) selects best LinkedIn `/company/` URL and extracts snippet. First Wikipedia link is taken.
3.  **Scraping:** Homepage HTML is fetched. `find_and_scrape_about_page_async` uses LLM/keywords to find and fetch the "About Us" page.
4.  **Wikipedia Fetch:** `get_wikipedia_summary_async` fetches the summary if a Wiki URL was found.
5.  **Text Extraction & Validation:** Text is extracted from "About Us" (priority 1), Wikipedia (priority 2), LinkedIn Snippet (priority 3), Homepage (priority 4, only if validated via `validate_page`).
6.  **Description Generation:** Combined text (marked by source) is sent to OpenAI via `generate_description_openai_async` (using `llm_config.yaml`).
7.  **Saving:** Result (with cleaned base URLs) is appended to the session's `results.csv`.

## 7. Project Structure

*   `app_ui.py`: **(New)** Main application file for the Tkinter GUI.
*   `src/`:
    *   `pipeline.py`: Contains `run_pipeline_for_file` (logic for processing one file) and `run_pipeline_cli` (for command-line execution).
    *   `config.py`: Loads `.env` keys and `llm_config.yaml`.
    *   `data_io.py`: Handles CSV reading/writing, context files, and now `sessions_metadata.json`.
    *   `processing.py`: Page validation, text extraction, About page finder, Wikipedia fetching.
    *   `external_apis/`: Modules for Serper, ScrapingBee, OpenAI.
*   `input/`: For original input data files.
*   `output/`:
    *   `sessions/`: **(New)** Stores all data related to individual processing sessions.
    *   `logs/`: (May become obsolete or used for UI logs only).
    *   `final_outputs/`: (May become obsolete if all output goes to sessions).
*   `requirements.txt`, `.env`, `llm_config.yaml`, `README.md`
*   `sessions_metadata.json`: **(New)** Stores metadata about each session.

## 8. Potential Issues and Debugging

*   See previous README section for common issues (API Keys, Dependencies, Site Access).
*   **UI Issues:** Ensure Tkinter is correctly installed with your Python distribution. Check console for errors when interacting with the UI.
*   **Threading Issues:** If the UI freezes indefinitely, there might be an unhandled error or deadlock in the `run_pipeline_in_thread` function. Check console output and session log files.
*   **Session File Errors:** Ensure `sessions_metadata.json` is valid JSON. Check file/folder permissions if saving fails.
