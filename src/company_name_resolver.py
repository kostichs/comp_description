"""
Company Name Resolution Module

This module handles the resolution of juridical names, founder names, emails,
and other indirect company identifiers into actual operating company names.
"""

import json
import logging
import re
import yaml
from typing import Dict, List, Any, Optional, Tuple
from openai import AsyncOpenAI
from pathlib import Path

logger = logging.getLogger(__name__)

class CompanyNameResolver:
    """
    Resolves various types of input data into actual company names.
    
    Handles:
    - Juridical/legal company names
    - Founder names or CEO names  
    - Email addresses or domains
    - Organization registration names
    - Subsidiary or division names
    """
    
    def __init__(self, config_path: str = "llm_company_resolution_config.yaml"):
        """
        Initialize the company name resolver.
        
        Args:
            config_path: Path to the resolution configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.openai_client = None
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded company resolution config from {self.config_path}")
                return config
        except Exception as e:
            logger.error(f"Error loading resolution config: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration if file loading fails."""
        return {
            "resolution_model": "gpt-4o-mini",
            "resolution_temperature": 0.1,
            "integration": {
                "enable_resolution_stage": False,
                "juridical_suffixes": ["Co., Ltd.", ", Inc.", ", LLC", "GmbH", "UAB"],
                "person_indicators": ["CEO", "Founder", "Mr.", "Dr."],
                "email_patterns": ["@", ".com"]
            },
            "validation_rules": {
                "min_confidence_to_proceed": "medium"
            }
        }
    
    def setup_openai_client(self, api_key: str):
        """Setup OpenAI client for resolution."""
        self.openai_client = AsyncOpenAI(api_key=api_key)
    
    def should_trigger_resolution(self, input_data: str) -> Tuple[bool, str]:
        """
        Determine if input data should trigger company name resolution.
        
        Args:
            input_data: The input string to analyze
            
        Returns:
            Tuple of (should_trigger, reason)
        """
        if not input_data or not isinstance(input_data, str):
            return False, "empty_or_invalid_input"
        
        input_lower = input_data.lower().strip()
        
        # Check for juridical suffixes
        juridical_suffixes = self.config.get("integration", {}).get("juridical_suffixes", [])
        for suffix in juridical_suffixes:
            if suffix.lower() in input_lower:
                return True, f"contains_juridical_suffix: {suffix}"
        
        # Check for email patterns
        email_patterns = self.config.get("integration", {}).get("email_patterns", [])
        for pattern in email_patterns:
            if pattern in input_lower:
                return True, f"contains_email_pattern: {pattern}"
        
        # Check for person indicators
        person_indicators = self.config.get("integration", {}).get("person_indicators", [])
        for indicator in person_indicators:
            if indicator.lower() in input_lower:
                return True, f"contains_person_indicator: {indicator}"
        
        # Check if it looks like a person's name (simple heuristic)
        words = input_data.split()
        if len(words) == 2 and all(word.istitle() for word in words):
            return True, "appears_to_be_person_name"
        
        return False, "no_trigger_conditions_met"
    
    async def resolve_company_name(self, input_data: str) -> Dict[str, Any]:
        """
        Resolve input data to actual company name.
        
        Args:
            input_data: The input string to resolve
            
        Returns:
            Dictionary with resolution results
        """
        if not self.openai_client:
            logger.error("OpenAI client not initialized")
            return self._create_failed_resolution(input_data, "openai_client_not_initialized")
        
        try:
            # Prepare the prompt
            user_prompt = self.config.get("resolution_user_prompt", "").format(
                input_data=input_data
            )
            
            system_prompt = self.config.get("resolution_system_prompt", "")
            
            # Make API call - check if using search model
            model_name = self.config.get("resolution_model", "gpt-4o-mini")
            
            if "search" in model_name.lower():
                # For search models, don't use temperature and use different parameters
                response = await self.openai_client.chat.completions.create(
                    model=model_name,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
            else:
                # For regular models, use temperature
                response = await self.openai_client.chat.completions.create(
                    model=model_name,
                    temperature=self.config.get("resolution_temperature", 0.1),
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
            
            # Parse response
            response_text = response.choices[0].message.content
            resolution_result = json.loads(response_text)
            
            # Validate and enhance result
            return self._validate_resolution_result(resolution_result, input_data)
            
        except Exception as e:
            logger.error(f"Error resolving company name for '{input_data}': {e}")
            return self._create_failed_resolution(input_data, f"api_error: {str(e)}")
    
    def _validate_resolution_result(self, result: Dict[str, Any], original_input: str) -> Dict[str, Any]:
        """
        Validate and enhance the resolution result.
        
        Args:
            result: Raw result from LLM
            original_input: Original input data
            
        Returns:
            Validated and enhanced result
        """
        # Ensure required fields exist
        validated_result = {
            "original_input": original_input,
            "identified_company_name": result.get("identified_company_name", ""),
            "confidence_level": result.get("confidence_level", "low"),
            "company_website": result.get("company_website", ""),
            "input_type": result.get("input_type", "other"),
            "reasoning": result.get("reasoning", ""),
            "should_proceed": result.get("should_proceed", False),
            "alternative_search_terms": result.get("alternative_search_terms", []),
            "search_summary": result.get("search_summary", ""),
            "resolution_successful": True,
            "resolution_error": None
        }
        
        # Validate confidence level
        valid_confidence_levels = ["high", "medium", "low"]
        if validated_result["confidence_level"] not in valid_confidence_levels:
            validated_result["confidence_level"] = "low"
        
        # Check minimum confidence requirement
        min_confidence = self.config.get("validation_rules", {}).get("min_confidence_to_proceed", "medium")
        confidence_order = {"low": 0, "medium": 1, "high": 2}
        
        if confidence_order.get(validated_result["confidence_level"], 0) < confidence_order.get(min_confidence, 1):
            validated_result["should_proceed"] = False
            validated_result["reasoning"] += f" (Below minimum confidence threshold: {min_confidence})"
        
        # Limit alternative search terms
        max_terms = self.config.get("validation_rules", {}).get("max_alternative_terms", 5)
        if len(validated_result["alternative_search_terms"]) > max_terms:
            validated_result["alternative_search_terms"] = validated_result["alternative_search_terms"][:max_terms]
        
        return validated_result
    
    def _create_failed_resolution(self, original_input: str, error_reason: str) -> Dict[str, Any]:
        """Create a failed resolution result."""
        return {
            "original_input": original_input,
            "identified_company_name": "",
            "confidence_level": "low",
            "company_website": "",
            "input_type": "unknown",
            "reasoning": f"Resolution failed: {error_reason}",
            "should_proceed": False,
            "alternative_search_terms": [],
            "search_summary": "",
            "resolution_successful": False,
            "resolution_error": error_reason
        }
    
    def get_final_company_name(self, resolution_result: Dict[str, Any]) -> str:
        """
        Get the final company name to use for processing.
        
        Args:
            resolution_result: Result from resolve_company_name
            
        Returns:
            Company name to use for further processing
        """
        if not resolution_result.get("should_proceed", False):
            # Use fallback strategy
            fallback_strategies = self.config.get("fallback_strategies", ["use_original_input"])
            
            if "use_original_input" in fallback_strategies:
                return resolution_result.get("original_input", "")
            else:
                return ""  # Skip processing
        
        return resolution_result.get("identified_company_name", resolution_result.get("original_input", ""))

# Utility functions for integration with existing pipeline

def should_use_company_resolution(input_data: str, config_path: str = "llm_company_resolution_config.yaml") -> bool:
    """
    Quick check if company resolution should be used for given input.
    
    Args:
        input_data: Input string to check
        config_path: Path to resolution config
        
    Returns:
        True if resolution should be used
    """
    try:
        resolver = CompanyNameResolver(config_path)
        should_trigger, _ = resolver.should_trigger_resolution(input_data)
        return should_trigger and resolver.config.get("integration", {}).get("enable_resolution_stage", False)
    except Exception as e:
        logger.error(f"Error checking if resolution should be used: {e}")
        return False

async def resolve_company_name_if_needed(
    input_data: str, 
    openai_client: AsyncOpenAI,
    config_path: str = "llm_company_resolution_config.yaml"
) -> Tuple[str, Dict[str, Any]]:
    """
    Resolve company name if needed, otherwise return original input.
    
    Args:
        input_data: Input string to potentially resolve
        openai_client: OpenAI client for API calls
        config_path: Path to resolution config
        
    Returns:
        Tuple of (final_company_name, resolution_metadata)
    """
    resolver = CompanyNameResolver(config_path)
    
    # Check if resolution is enabled and should be triggered
    if not resolver.config.get("integration", {}).get("enable_resolution_stage", False):
        return input_data, {"resolution_used": False, "reason": "resolution_disabled"}
    
    should_trigger, trigger_reason = resolver.should_trigger_resolution(input_data)
    if not should_trigger:
        return input_data, {"resolution_used": False, "reason": trigger_reason}
    
    # Perform resolution
    resolver.setup_openai_client(openai_client.api_key)
    resolution_result = await resolver.resolve_company_name(input_data)
    final_name = resolver.get_final_company_name(resolution_result)
    
    resolution_metadata = {
        "resolution_used": True,
        "trigger_reason": trigger_reason,
        "resolution_result": resolution_result,
        "final_name": final_name
    }
    
    logger.info(f"Company resolution: '{input_data}' → '{final_name}' (confidence: {resolution_result.get('confidence_level', 'unknown')})")
    
    return final_name, resolution_metadata 