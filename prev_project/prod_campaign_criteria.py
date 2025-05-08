import os
import time
import json
import pandas as pd
import yaml
from dotenv import load_dotenv
import os
import tkinter as tk
import tkinter.simpledialog as simpledialog
from tkinter import filedialog, messagebox
from configparser import ConfigParser
from openai import OpenAI

# === DIR ===
##BASE_DIR = "C:/Users/Mikhail Loviagin/PyCharmMiscProject/VM_campaigns_information" ##основной путь
##ENV_PATH = os.path.join(BASE_DIR, ".env") ##файл с ключами
##CFG_PATH = os.path.join(BASE_DIR, "LLM.cfg") ##конфиг для моделей
##YAML_PATH = os.path.join(BASE_DIR, "promt_generate.yaml") ##промт для моделей
##INPUT_PATH = os.path.join(BASE_DIR, "output", "companies_wikipedia_website_linkedin.csv")
##CRITERIA_PATH = os.path.join(BASE_DIR, "input", "VM_Target Audience Criteria-2.csv")
##QUALIFICATION_PATH = os.path.join(BASE_DIR, "input", "qualification_questions_VM.csv")
##JSON_OUTPUT_PATH = os.path.join(BASE_DIR, "output", "companies_output.json")

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
    title="Select input CSV required fields Company_Name;Wikipedia_URL;Official_Website;LinkedIn_URL;Description",
    filetypes=[("CSV files", "*.csv")]
)

CRITERIA_PATH = filedialog.askopenfilename(
    title="Select target audience criteria CSV required fields Product;Target Audience;Criteria Type;Criteria",
    filetypes=[("CSV files", "*.csv")]
)

QUALIFICATION_PATH = filedialog.askopenfilename(
    title="Select qualification questions CSV required fields Target Audience;Qualification Question",
    filetypes=[("CSV files", "*.csv")]
)

# === Directory for output JSON ===
JSON_OUTPUT_PATH = filedialog.asksaveasfilename(
    title="Select output JSON file",
    defaultextension=".json",
    filetypes=[("JSON files", "*.json")],
    initialfile="companies_output.json"
)

# === Validate file selections ===
if not all([INPUT_PATH, CRITERIA_PATH, QUALIFICATION_PATH, JSON_OUTPUT_PATH]):
    raise Exception("❌ One or more input/output files were not selected.")


# === API KEYS ===
load_dotenv(dotenv_path=ENV_PATH)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === CFG LLM MODEL ===
cfg = ConfigParser()
cfg.read(CFG_PATH)
criterion_model = cfg.get("models", "criterion_model")

# === OpenAI client ===
client = OpenAI(api_key=OPENAI_API_KEY)

# === PROMT FROM YAML ===
with open(YAML_PATH, "r", encoding="utf-8") as f:
    prompts = yaml.safe_load(f)

general_prompt_template = prompts.get("general_criterion_prompt")
qualification_prompt_template = prompts.get("qualification_criterion_prompt")
mandatory_prompt_template = prompts.get("nth_mandatory_criterion_prompt")
nth_prompt_template = prompts.get("nth_mandatory_criterion_prompt")

# === UPLOAD DATA ===
df_companies = pd.read_csv(INPUT_PATH, sep=";", encoding="utf-8-sig")
df_criteria = pd.read_csv(CRITERIA_PATH, sep=";", encoding="utf-8-sig")
df_qual = pd.read_csv(QUALIFICATION_PATH, sep=";", encoding="utf-8-sig")


# === How many companies to process (default 10) ===
limit_input = simpledialog.askstring(
    title="Campaign processing limit",
    prompt="How many companies to process?\n(Default: 10 — clear input to process ALL)",
    initialvalue="10"
)
try:
    limit = int(limit_input)
except (ValueError, TypeError):
    limit = None  # If cleared or invalid → process all

# === Filter companies by selected limit ===
df_companies = df_companies.dropna(subset=["Company_Name"])
companies = df_companies.iloc[:limit] if limit else df_companies

# === Criteria Type ===
general_criteria = df_criteria[df_criteria["Criteria Type"] == "General"]["Criteria"].dropna().tolist()
mandatory_df = df_criteria[df_criteria["Criteria Type"] == "Mandatory"].dropna(subset=["Criteria", "Target Audience"])
nth_df = df_criteria[df_criteria["Criteria Type"] == "NTH"].dropna(subset=["Criteria", "Target Audience"])

qualification_questions = {
    row["Target Audience"]: row["Qualification Question"]
    for _, row in df_qual.iterrows()
}

# === Functions with LLM models ===
def ask_openai(prompt):
    response = client.chat.completions.create(
        model=criterion_model,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

def check_general_criteria(description, info):
    all_passed = True
    for criterion in general_criteria:
        prompt = general_prompt_template.format(description=description, criterion=criterion)
        print(f"🧪 General: {criterion}")
        try:
            result = ask_openai(prompt)
            print(f"➡️  {result}")
            key = f"General_{'Passed' if result == 'Passed' else 'Skipped'}_{criterion}"
            info[key] = result
            if result != "Passed":
                all_passed = False
        except Exception as e:
            print(f"❌ Error General: {e}")
            info[f"General_Skipped_{criterion}"] = "Error"
            all_passed = False
    return all_passed

def check_qualification_questions(description, company_info):
    for audience, question in qualification_questions.items():
        prompt = qualification_prompt_template.format(description=description, question=question)
        print(f"🔍 Qualification [{audience}]: {question}")
        try:
            result = ask_openai(prompt).strip().lower()
            answer = "Yes" if result.startswith("yes") else "No"
            company_info[f"Qualification_{audience}"] = answer
        except Exception as e:
            company_info[f"Qualification_{audience}"] = "ND"
            print(f"❌ Error Qualification {audience}: {e}")

def check_mandatory_criteria(description, company_info, audience):
    mandatory = mandatory_df[mandatory_df["Target Audience"] == audience]
    failed = False
    nd_count = 0
    total = 0
    for row in mandatory.itertuples():
        crit = row.Criteria
        prompt = mandatory_prompt_template.format(description=description, criterion=crit)
        result = ask_openai(prompt)
        company_info[f"Mandatory_{audience}_{crit}"] = result
        print(f"⚠️  Mandatory {audience}: {crit} => {result}")
        if result == "Not Passed":
            failed = True
        if result == "ND":
            nd_count += 1
        total += 1
        if failed:
            break
    if total > 0:
        company_info[f"%ND Mandatory_{audience}"] = round(nd_count / total, 2)
    return not failed

def check_nth_criteria(description, company_info, audience):
    nth = nth_df[nth_df["Target Audience"] == audience]
    passed_count = 0
    total = 0
    for row in nth.itertuples():
        crit = row.Criteria
        prompt = nth_prompt_template.format(description=description, criterion=crit)
        result = ask_openai(prompt)
        company_info[f"NTH_{audience}_{crit}"] = result
        print(f"✨ NTH {audience}: {crit} => {result}")
        if result == "Passed":
            passed_count += 1
        total += 1
    if total > 0:
        company_info[f"%NTH Passed_{audience}"] = round(passed_count / total, 2)

# === Main Cycle ===
results = []

for row in companies.itertuples():
    company = row.Company_Name
    description = row.Description
    print(f"\n🚀 Campaign: {company}")

    info = {
        "Company_Name": company,
        "Description": description,
        "Wikipedia_URL": getattr(row, "Wikipedia_URL", ""),
        "Official_Website": getattr(row, "Official_Website", ""),
        "LinkedIn_URL": getattr(row, "LinkedIn_URL", "")
    }

    if not check_general_criteria(description, info):
        info["General_Criteria_Status"] = "Skipped - General criteria not passed"
        results.append(info)
        continue

    info["General_Criteria_Status"] = "Passed"
    check_qualification_questions(description, info)

    for audience in qualification_questions:
        q_col = f"Qualification_{audience}"
        if info.get(q_col, "").lower() != "yes":
            continue

        print(f"🧱 Check Criteria for {audience}")
        if not check_mandatory_criteria(description, info, audience):
            print("⛔ Skipping the NTH due to an error in Mandatory")
            continue
        check_nth_criteria(description, info, audience)

    results.append(info)

# === Save JSON ===
with open(JSON_OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n✅ Saved: {JSON_OUTPUT_PATH}")
