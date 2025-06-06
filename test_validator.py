"""
Test script for result validator
"""

import asyncio
import logging
from openai import AsyncOpenAI
from src.validators.result_validator import validate_company_result

# Configure logging
logging.basicConfig(level=logging.INFO)

async def test_validator():
    """Test the result validator with different scenarios"""
    
    # Initialize OpenAI client
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_api_key:
        print("OPENAI_API_KEY not found in environment")
        return
    
    client = AsyncOpenAI(api_key=openai_api_key)
    
    # Test cases
    test_cases = [
        {
            "name": "Person name should fail",
            "original_query": "vladimir.porokhov",
            "company_data": {
                "company_name": "GitHub, Inc.",
                "description": "GitHub is a web-based platform for version control...",
                "official_website": "https://github.com",
                "linkedin_url": ""
            }
        },
        {
            "name": "Matching company should pass",
            "original_query": "GitHub",
            "company_data": {
                "company_name": "GitHub, Inc.",
                "description": "GitHub is a web-based platform for version control...",
                "official_website": "https://github.com",
                "linkedin_url": ""
            }
        },
        {
            "name": "Different company should fail",
            "original_query": "Apple",
            "company_data": {
                "company_name": "Microsoft Corporation",
                "description": "Microsoft Corporation is an American multinational...",
                "official_website": "https://microsoft.com",
                "linkedin_url": ""
            }
        },
        {
            "name": "Similar company names should pass",
            "original_query": "Apple Inc",
            "company_data": {
                "company_name": "Apple Inc.",
                "description": "Apple Inc. is an American multinational technology...",
                "official_website": "https://apple.com",
                "linkedin_url": ""
            }
        }
    ]
    
    print("Testing result validator...")
    print("=" * 50)
    
    for test_case in test_cases:
        print(f"\nTest: {test_case['name']}")
        print(f"Query: {test_case['original_query']}")
        print(f"Found: {test_case['company_data']['company_name']}")
        
        try:
            result = await validate_company_result(
                openai_client=client,
                original_query=test_case['original_query'],
                company_data=test_case['company_data']
            )
            
            validation = result.get('validation', {})
            is_valid = validation.get('is_valid', False)
            reason = validation.get('validation_reason', 'No reason provided')
            
            print(f"Valid: {is_valid}")
            print(f"Reason: {reason}")
            print("-" * 30)
            
        except Exception as e:
            print(f"Error: {e}")
            print("-" * 30)

if __name__ == "__main__":
    asyncio.run(test_validator()) 