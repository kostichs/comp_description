import os
import time
import pandas as pd
import requests
from configparser import ConfigParser
from dotenv import load_dotenv
import tkinter as tk
import tkinter.simpledialog as simpledialog
from tkinter import filedialog, messagebox
from openai import OpenAI
import yaml
import google.generativeai as genai  # for testing free

# === DIR ===
##BASE_DIR = "C:/Users/Mikhail Loviagin/PyCharmMiscProject/VM_campaigns_information"
##ENV_PATH = os.path.join(BASE_DIR, ".env")
##CFG_PATH = os.path.join(BASE_DIR, "LLM.cfg")
##YAML_PATH = os.path.join(BASE_DIR, "promt_generate.yaml")

##INPUT_PATH = os.path.join(BASE_DIR, "input", "Find-Companies-Table-Default-view-export-1746527738033_1.csv")
##OUTPUT_PATH = os.path.join(BASE_DIR, "output", "companies_wikipedia_website_linkedin.csv")

# === GUI: select base project directory ===
tk.Tk().withdraw()

messagebox.showinfo(
    title="SELECT PROJECT DIRECTORY",
    message="PLEASE SELECT THE FOLDER THAT CONTAINS:\n.env, LLM.cfg, promt_generate.yaml"
)

BASE_DIR = filedialog.askdirectory(title="SELECT WORKING DIRECTORY")
if not BASE_DIR:
    raise Exception("❌ No directory selected. Exiting.")

# === Check required config files in selected directory ===
required_files = {
    "ENV_PATH": ".env",
    "CFG_PATH": "LLM.cfg",
    "YAML_PATH": "promt_generate.yaml"
}

paths = {}
missing = []

for key, filename in required_files.items():
    full_path = os.path.join(BASE_DIR, filename)
    if not os.path.isfile(full_path):
        missing.append(filename)
    paths[key] = full_path

if missing:
    raise FileNotFoundError(f"❌ Missing required files: {', '.join(missing)}")

ENV_PATH = paths["ENV_PATH"]
CFG_PATH = paths["CFG_PATH"]
YAML_PATH = paths["YAML_PATH"]

# === Select input/output files manually ===
INPUT_PATH = filedialog.askopenfilename(
    title="Select input CSV required fields Company_Name",
    filetypes=[("CSV files", "*.csv")]
)

OUTPUT_PATH = filedialog.asksaveasfilename(
    title="Select output CSV file",
    defaultextension=".csv",
    filetypes=[("CSV files", "*.csv")],
    initialfile="companies_wikipedia_website_linkedin.csv"
)

# === Validate file selections ===
if not all([INPUT_PATH, OUTPUT_PATH]):
    raise Exception("❌ One or more input/output files were not selected.")

# === API KEYS ===
load_dotenv(dotenv_path=ENV_PATH)
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") ## for testing free model gemini-2.5-flash-preview-04-17

# === CFG LLM MODEL ===
cfg = ConfigParser()
cfg.read(CFG_PATH)
description_model = cfg.get("models", "description_model")

# === OpenAI client ===
client = OpenAI(api_key=OPENAI_API_KEY)

# === PROMT FROM YAML ===
with open(YAML_PATH, "r", encoding="utf-8") as f:
    prompts = yaml.safe_load(f)
    prompt_template = prompts.get("generate_description_prompt")
if prompt_template is None:
    raise ValueError("❌ The 'generate_description_prompt' key is missing in the YAML file")

# === Function: Search from SERPER API ===
def serper_search(company, keyword):
    query = f"{company} {keyword}"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    response = requests.post(
        "https://google.serper.dev/search",
        headers=headers,
        json={"q": query}
    )
    data = response.json()
    for result in data.get("organic", []):
        link = result.get("link", "")
        if keyword == "wikipedia" and "wikipedia.org" in link:
            return link
        if keyword == "official website" and not any(s in link for s in ["wikipedia.org", "linkedin.com"]):
            return link
        if keyword == "linkedin site:linkedin.com" and "linkedin.com/company" in link:
            return link
    return "not found"

# === FUNCTION GENERATION DESCRIPTION BY LLM BASED ON STATIC INFORMATION ===
def generate_description(company, wikipedia_url, website_url, linkedin_url):
    prompt = prompt_template.format (
        company=company,
        wikipedia_url=wikipedia_url,
        website_url=website_url,
        linkedin_url=linkedin_url
    )
    try:
        response = client.chat.completions.create(
            model=description_model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ description generation error: {e}")
        return ""

# === Load input and ask for processing limit ===
df = pd.read_csv(INPUT_PATH)
df = df.dropna(subset=["Company_Name"])

limit_input = simpledialog.askstring(
    title="Campaign processing limit",
    prompt="How many companies to process?\n(Default: 10 — clear input to process ALL)",
    initialvalue="10"
)

try:
    limit = int(limit_input)
except (ValueError, TypeError):
    limit = None

if limit:
    df = df.iloc[:limit]

results = []

for row in df.itertuples():
    company = row.Company_Name
    print(f"🔍 Processing: {company}")
    result_row = {"Company_Name": company}

    # Wikipedia
    result_row["Wikipedia_URL"] = getattr(row, "Wikipedia_URL", "") or serper_search(company, "wikipedia")
    # Website
    result_row["Official_Website"] = getattr(row, "Official_Website", "") or serper_search(company, "official website")
    # LinkedIn
    result_row["LinkedIn_URL"] = getattr(row, "LinkedIn_URL", "") or serper_search(company, "linkedin site:linkedin.com")
    # Description
    time.sleep(2)
    result_row["Description"] = generate_description(
        company,
        result_row["Wikipedia_URL"],
        result_row["Official_Website"],
        result_row["LinkedIn_URL"]
    )

    results.append(result_row)
    print(f"✅ Done: {company}")

# === Saving the result===
df_out = pd.DataFrame(results)
df_out.to_csv(OUTPUT_PATH, sep=";", index=False, encoding="utf-8-sig")
print(f"\n✅ File is saved: {OUTPUT_PATH}")
