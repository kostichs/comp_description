## 📘 README: VM Campaigns Evaluation Pipeline

This project includes two primary Python scripts that process B2B SaaS companies in two main stages:

---

### 🧩 1. `prod_parser_campaign_information.py`
**Purpose:** Parse and generate enriched data for companies:  
- Wikipedia URL  
- Official Website  
- LinkedIn URL  
- LLM-generated company description

#### 📅 Input:
- A CSV file with a `Company_Name` column.

#### 🧠 What it does:
- Uses Serper.dev API to find relevant URLs (Wikipedia, website, LinkedIn);
- Uses an LLM model (defined in `LLM.cfg`) to generate a structured company description;
- Outputs a CSV with the following columns:
  - `Company_Name`
  - `Wikipedia_URL`
  - `Official_Website`
  - `LinkedIn_URL`
  - `Description`

#### ⚙️ Required files in selected folder:
- `.env` with keys: `OPENAI_API_KEY`, `SERPER_API_KEY`, `GEMINI_API_KEY`
- `LLM.cfg` with model configuration:
  ```ini
  [models]
  description_model = gpt-4o-mini-search-preview
  ```
- `promt_generate.yaml` with key: `generate_description_prompt`

#### 📀 Output:
Saved to `companies_wikipedia_website_linkedin.csv`

---

### ✅ 2. `prod_campaign_criteria.py`
**Purpose:** Evaluate companies against business criteria:
- General
- Qualification Questions
- Mandatory
- Nice-to-Have (NTH)

#### 📅 Input:
- CSV from stage 1 (`companies_wikipedia_website_linkedin.csv`)
- Target audience criteria CSV: includes Product, Target Audience, Criteria Type, and Criteria
- Qualification questions CSV

#### 🧠 What it does:
- Loads company description and metadata;
- Validates against general criteria (stops if any fail);
- Evaluates qualification questions;
- Proceeds to Mandatory and NTH checks if qualified;
- Uses OpenAI model defined in `LLM.cfg`:
  ```ini
  [models]
  criterion_model = gpt-4o-mini
  ```

#### 🗒 YAML keys used:
- `general_criterion_prompt`
- `qualification_criterion_prompt`
- `nth_mandatory_criterion_prompt`

#### 📀 Output:
- Saved as JSON: `companies_output.json`
- Includes full evaluation results, status flags, and statistics such as % NTH Passed

---

### 🛠 ️ How to run:

1. Run `prod_parser_campaign_information.py`
   - Select input CSV with `Company_Name` field;
   - Select folder containing `.env`, `LLM.cfg`, and `promt_generate.yaml`;
   - Choose path for output CSV file.

2. Run `prod_campaign_criteria.py`
   - Select the CSV generated from step 1;
   - Select CSV files for criteria and qualification questions;
   - Select output location for final JSON.

---

### ✅ Requirements:
- Python 3.10+
- Install dependencies:
  ```bash
  pip install openai python-dotenv pyyaml pandas requests time configparser tkinter tkinter.simpledialog
  ```
