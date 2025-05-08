import asyncio
import os
import traceback
import sys

# Add src directory to Python path to allow imports like 'from src.pipeline import run_pipeline'
# This makes the script runnable directly as 'python main.py'
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Now import from the src package
try:
    from src.pipeline import run_pipeline
except ImportError as e:
    print(f"Error importing from src package: {e}")
    print("Ensure the script is run from the project root directory containing 'main.py' and the 'src/' folder.")
    sys.exit(1)

if __name__ == "__main__":
    # Set policy for Windows if needed (often helps with aiohttp/asyncio)
    if os.name == 'nt':
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            print("Windows asyncio policy set.")
        except Exception as policy_err:
            print(f"Warning: Could not set WindowsSelectorEventLoopPolicy - {policy_err}")

    try:
        print("Starting application...")
        asyncio.run(run_pipeline())
        print("Application finished successfully.")
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred in the main execution: {e}")
        traceback.print_exc()
        sys.exit(1) # Exit with error code on unhandled exception 
        