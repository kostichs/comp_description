"""
Result Validator Module

Validates if the found company information matches the original query
"""

import logging
from typing import Dict, Any, Optional, Tuple
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class ResultValidator:
    """Validates company search results for relevance and accuracy"""
    
    def __init__(self, openai_client: AsyncOpenAI):
        self.openai_client = openai_client
    
    async def validate_result(
        self, 
        original_query: str, 
        found_company_name: str, 
        company_description: str,
        found_website: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Validate if the found company information matches the original query
        
        Args:
            original_query: Original company name/query from user
            found_company_name: Company name found in the description
            company_description: Full company description
            found_website: Website URL if found
            
        Returns:
            Tuple of (is_valid, reason, suggested_action)
        """
        
        # Quick checks first
        if self._is_person_name(original_query):
            return False, f"'{original_query}' appears to be a person's name, not a company", "skip"
        
        if not found_company_name or not company_description:
            return False, "Empty or invalid company information found", "skip"
        
        # LLM-based validation
        try:
            validation_result = await self._llm_validate(
                original_query, 
                found_company_name, 
                company_description,
                found_website
            )
            return validation_result
            
        except Exception as e:
            logger.error(f"Error during LLM validation: {e}")
            # Fallback to simple string matching
            return self._simple_validation(original_query, found_company_name)
    
    def _is_person_name(self, query: str) -> bool:
        """Check if query looks like a person's name"""
        query_lower = query.lower().strip()
        
        # Skip common business entity suffixes 
        business_suffixes = {'inc', 'ltd', 'llc', 'corp', 'corporation', 'company', 'co', 'limited'}
        words = query_lower.split()
        
        # If contains business suffix, it's likely a company
        if any(word.rstrip('.') in business_suffixes for word in words):
            return False
        
        # Common patterns for person names
        person_indicators = [
            # Has common name patterns like john.doe
            len(query.split('.')) >= 2 and all(len(part) > 1 for part in query.split('.')),  # john.doe
            query_lower.endswith(('.jr', '.sr', '.iii', '.ii')),  # John Doe Jr.
        ]
        
        # Check for two words where both are alphabetic (but not business entity)
        if len(words) == 2 and all(word.isalpha() for word in words):
            # Common first names (basic check)
            common_first_names = {
                'john', 'jane', 'michael', 'sarah', 'david', 'mary', 'robert', 'jennifer',
                'vladimir', 'dmitry', 'alexander', 'elena', 'sergey', 'natasha', 'pavel',
                'olga', 'igor', 'anna', 'alexey', 'maria', 'andrey', 'svetlana'
            }
            
            first_word = words[0]
            if first_word in common_first_names:
                person_indicators.append(True)
        
        return any(person_indicators)
    
    async def _llm_validate(
        self, 
        original_query: str, 
        found_company_name: str, 
        company_description: str,
        found_website: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """Use LLM to validate if the found information matches the query"""
        
        website_info = f"\nFound website: {found_website}" if found_website else ""
        
        validation_prompt = f"""
You are a company information validator. Your task is to determine if the found company information matches the original search query.

ORIGINAL QUERY: "{original_query}"
FOUND COMPANY NAME: "{found_company_name}"
FOUND WEBSITE: {found_website or "Not found"}{website_info}

FOUND DESCRIPTION (first 500 chars):
{company_description[:500]}...

Please analyze if this found information is relevant to the original query. Consider:

1. Is the original query actually a company name (not a person's name)?
2. Does the found company name relate to the original query?
3. Could this be the right company despite name differences (subsidiaries, acquisitions, etc.)?
4. Is this information completely unrelated to the original query?

Respond with EXACTLY this format:
VALID: [YES/NO]
CONFIDENCE: [HIGH/MEDIUM/LOW]
REASON: [Brief explanation]
ACTION: [ACCEPT/REJECT/MANUAL_REVIEW]

Examples:
- If original query is "Apple Inc" and found is "Apple Inc." -> VALID: YES
- If original query is "john.smith" and found is "GitHub" -> VALID: NO  
- If original query is "Acme Corp" and found is "Acme Corporation" -> VALID: YES
- If original query is "StartupXYZ" and found is "Microsoft" -> VALID: NO
"""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a precise company information validator."},
                    {"role": "user", "content": validation_prompt}
                ],
                temperature=0.1,
                max_tokens=300
            )
            
            result_text = response.choices[0].message.content.strip()
            return self._parse_llm_response(result_text, original_query, found_company_name)
            
        except Exception as e:
            logger.error(f"LLM validation failed: {e}")
            raise
    
    def _parse_llm_response(
        self, 
        response: str, 
        original_query: str, 
        found_company_name: str
    ) -> Tuple[bool, str, Optional[str]]:
        """Parse LLM validation response"""
        
        lines = response.split('\n')
        valid = False
        reason = "LLM validation completed"
        action = "reject"
        
        for line in lines:
            line = line.strip()
            if line.startswith('VALID:'):
                valid = 'YES' in line.upper()
            elif line.startswith('REASON:'):
                reason = line.replace('REASON:', '').strip()
            elif line.startswith('ACTION:'):
                action_text = line.replace('ACTION:', '').strip().lower()
                if 'accept' in action_text:
                    action = "accept"
                elif 'manual' in action_text:
                    action = "manual_review"
                else:
                    action = "reject"
        
        # Override action based on validation result
        if valid:
            suggested_action = "accept"
        else:
            suggested_action = "reject"
            
        logger.info(f"Validation result for '{original_query}' -> '{found_company_name}': {valid} ({reason})")
        
        return valid, reason, suggested_action
    
    def _simple_validation(self, original_query: str, found_company_name: str) -> Tuple[bool, str, Optional[str]]:
        """Fallback simple validation based on string similarity"""
        
        # Clean up names for comparison
        original_clean = self._clean_company_name(original_query)
        found_clean = self._clean_company_name(found_company_name)
        
        # Check if they're similar enough
        if original_clean.lower() in found_clean.lower() or found_clean.lower() in original_clean.lower():
            return True, "Names are similar (fallback validation)", "accept"
        
        # Check for very different names
        if len(original_clean) > 3 and len(found_clean) > 3:
            # If names are completely different and both are substantial
            return False, f"Names too different: '{original_query}' vs '{found_company_name}' (fallback validation)", "reject"
        
        # Default to accepting if unsure (conservative approach)
        return True, "Uncertain match, accepting conservatively (fallback validation)", "manual_review"
    
    def _clean_company_name(self, name: str) -> str:
        """Clean company name for comparison"""
        # Remove common suffixes
        suffixes = ['inc', 'corp', 'ltd', 'llc', 'co', 'company', 'corporation', 'limited']
        
        # Remove punctuation and normalize
        import re
        cleaned = re.sub(r'[^\w\s]', ' ', name.lower())
        words = cleaned.split()
        
        # Remove suffixes
        filtered_words = [w for w in words if w not in suffixes]
        
        return ' '.join(filtered_words).strip()

# Validation helper function for pipeline integration
async def validate_company_result(
    openai_client: AsyncOpenAI,
    original_query: str,
    company_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate company result and return enriched data with validation info
    
    Args:
        openai_client: OpenAI client instance
        original_query: Original company search query
        company_data: Company data dictionary with description, website, etc.
        
    Returns:
        Enhanced company data with validation information
    """
    
    validator = ResultValidator(openai_client)
    
    # Extract relevant fields
    found_company_name = company_data.get('company_name', '')
    description = company_data.get('description', '')
    website = company_data.get('official_website', '')
    
    # Perform validation
    is_valid, reason, suggested_action = await validator.validate_result(
        original_query=original_query,
        found_company_name=found_company_name,
        company_description=description,
        found_website=website
    )
    
    # Add validation info to company data
    validation_info = {
        'validation_performed': True,
        'is_valid': is_valid,
        'validation_reason': reason,
        'suggested_action': suggested_action,
        'original_query': original_query
    }
    
    # Create enhanced copy
    enhanced_data = company_data.copy()
    enhanced_data['validation'] = validation_info
    
    # If invalid, mark the result appropriately
    if not is_valid:
        enhanced_data['status'] = 'validation_failed'
        enhanced_data['error_message'] = f"Validation failed: {reason}"
        logger.warning(f"Validation failed for '{original_query}': {reason}")
    
    return enhanced_data 