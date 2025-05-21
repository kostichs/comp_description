#!/usr/bin/env python3
"""
Main entry point for running the company description pipeline
"""

import asyncio
import argparse
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
    parser = argparse.ArgumentParser(description="Run the company description pipeline")
    parser.add_argument("--input", "-i", help="Input CSV file path", default="test_companies.csv")
    parser.add_argument("--config", "-c", help="Configuration file path", default="llm_config.yaml")
    parser.add_argument("--use-hubspot", action="store_true", help="Enable HubSpot integration")
    parser.add_argument("--disable-hubspot", action="store_false", dest="use_hubspot", help="Disable HubSpot integration")
    parser.set_defaults(use_hubspot=None)  # None means use the config file setting
    
    args = parser.parse_args()
    
    # Import here to avoid circular imports
    from src.pipeline import run_pipeline
    
    logger.info(f"Starting pipeline with input file: {args.input}")
    
    # Run the pipeline
    success_count, failure_count, results = await run_pipeline(
        config_path=args.config,
        input_file=args.input,
        use_hubspot=args.use_hubspot
    )
    
    logger.info(f"Pipeline completed. Success: {success_count}, Failure: {failure_count}")
    
    return 0

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Pipeline terminated by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}", exc_info=True)
        sys.exit(1)
    sys.exit(0) 