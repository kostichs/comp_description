import os
import yaml
from dotenv import load_dotenv

def load_env_vars() -> tuple[str | None, str | None, str | None]:
    """Loads required API keys from .env file."""
    load_dotenv()
    scrapingbee_api_key = os.getenv("SCRAPINGBEE_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    serper_api_key = os.getenv("SERPER_API_KEY")
    
    missing_keys = []
    if not serper_api_key: missing_keys.append("SERPER_API_KEY")
    if not scrapingbee_api_key: missing_keys.append("SCRAPINGBEE_API_KEY")
    if not openai_api_key: missing_keys.append("OPENAI_API_KEY")
    
    if missing_keys:
        print(f"Error: Missing API keys in .env: {', '.join(missing_keys)}. Please set them.")
        # Raise an exception or return None to signal failure clearly
        # raise ValueError(f"Missing API keys: {', '.join(missing_keys)}")
        return None, None, None # Indicate failure
        
    return scrapingbee_api_key, openai_api_key, serper_api_key

def load_llm_config(config_path="llm_config.yaml") -> dict | None:
    """Loads the ENTIRE content of the YAML configuration file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        if isinstance(config, dict) and 'model' in config:
            print(f"LLM configuration loaded successfully from {config_path}")
            return config 
        elif isinstance(config, dict):
             print(f"Error: LLM config file {config_path} is missing required 'model' key.")
             return None
        else:
             print(f"Error: Content of LLM config file {config_path} is not a dictionary."); 
             return None
    except FileNotFoundError: print(f"Error: LLM config file {config_path} not found."); return None
    except yaml.YAMLError as e: print(f"Error parsing LLM config file {config_path}: {e}"); return None
    except Exception as e: print(f"Error loading LLM config {config_path}: {e}"); return None 