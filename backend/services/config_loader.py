"""
Configuration and API Keys Loader

Handles loading of:
- Environment variables and API keys
- LLM configuration from YAML
- Client initialization (OpenAI, ScrapingBee)
"""

import logging
from pathlib import Path
from openai import AsyncOpenAI
from src.config import load_env_vars, load_llm_config
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient

logger = logging.getLogger(__name__)

class ConfigLoader:
    """Handles loading and validation of configuration and API keys"""
    
    def __init__(self):
        self.scrapingbee_api_key = None
        self.openai_api_key = None
        self.serper_api_key = None
        self.hubspot_api_key = None
        self.llm_config = None
        self.openai_client = None
        self.sb_client = None
    
    async def load_config(self, config_path: str = "llm_config.yaml"):
        """Load all configuration and initialize clients"""
        try:
            # Load API keys
            self.scrapingbee_api_key, self.openai_api_key, self.serper_api_key, self.hubspot_api_key = load_env_vars()
            
            # Load LLM config
            self.llm_config = load_llm_config(config_path)
            
            # Validate required keys
            if not all([self.scrapingbee_api_key, self.openai_api_key, self.serper_api_key, self.llm_config]):
                raise ValueError("One or more required API keys or LLM config missing.")
            
            logger.info("Configuration loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Config loading failed: {e}")
            raise
    
    async def initialize_clients(self):
        """Initialize API clients"""
        try:
            self.openai_client = AsyncOpenAI(api_key=self.openai_api_key)
            self.sb_client = CustomScrapingBeeClient(api_key=self.scrapingbee_api_key)
            
            logger.info("API clients initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"API Client initialization failed: {e}")
            raise
    
    def get_api_keys_dict(self):
        """Get API keys as dictionary for pipeline adapter"""
        return {
            "openai": self.openai_api_key,
            "serper": self.serper_api_key,
            "scrapingbee": self.scrapingbee_api_key,
            "hubspot": self.hubspot_api_key
        } 