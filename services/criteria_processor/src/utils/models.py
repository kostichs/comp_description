import json
import yaml
from openai import OpenAI
from config import OPENAI_API_KEY, YAML_PATH

# Model configuration
CRITERION_MODEL = "gpt-4o-mini"

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Load prompts from YAML file
def load_prompts():
    """Load prompt templates from YAML file"""
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        prompts = yaml.safe_load(f)
    
    return {
        "general": prompts.get("general_criterion_prompt"),
        "qualification": prompts.get("qualification_criterion_prompt"),
        "mandatory": prompts.get("nth_mandatory_criterion_prompt"),
        "nth": prompts.get("nth_mandatory_criterion_prompt")
    }

# OpenAI API interaction with structured JSON response
def ask_openai_structured(prompt, schema):
    """Send a prompt to OpenAI and get a structured JSON response"""
    response = client.chat.completions.create(
        model=CRITERION_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={
            "type": "json_schema",
            "json_schema": schema
        }
    )
    return json.loads(response.choices[0].message.content) 