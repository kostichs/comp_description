#!/usr/bin/env python3
"""
Test script for the new pipeline structure
"""

import asyncio
import logging
import sys
from pathlib import Path

# Set up basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

async def main():
    logger.info("Testing new pipeline structure")
    
    try:
        # Import the run_pipeline function
        from src.pipeline import run_pipeline
        
        # Run the pipeline with test data
        logger.info("Running pipeline with test data")
        
        test_file = "test_companies.csv"
        if not Path(test_file).exists():
            logger.info(f"Test file {test_file} not found, creating a simple one")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("Company_Name,Official_Website\n")
                f.write("Test Company 1,https://example.com\n")
                f.write("Test Company 2,https://example.org\n")
        
        # Run the pipeline
        success_count, failure_count, results = await run_pipeline(
            input_file=test_file
        )
        
        logger.info(f"Pipeline test completed. Success: {success_count}, Failure: {failure_count}")
        logger.info(f"Results: {results}")
        
        return 0
    except Exception as e:
        logger.error(f"Error testing new pipeline structure: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Test terminated by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1) 