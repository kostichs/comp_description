#!/usr/bin/env python3
"""
JSON Extractor for CSV Files

This script extracts JSON data from the last column of a CSV file and creates separate columns
for each JSON field. It's particularly useful for processing criteria output files where
JSON data is stored in a single column.

Features:
- Automatically processes the most recent non-expanded CSV file in the output directory
- Handles nested JSON structures
- Cleans up column names by removing special characters like '%'
- Creates an expanded CSV file with all JSON fields as separate columns
- Provides detailed error messages for problematic JSON data

Usage:
  python json_extractor.py                    # Process the latest CSV file in the output directory
  python json_extractor.py <file_path>        # Process a specific CSV file
  python json_extractor.py --help             # Show this help message
"""

import os
import sys
import json
import pandas as pd
import glob
from pathlib import Path

def extract_json_to_columns(input_file, output_file=None):
    """
    Extract JSON data from the last column of a CSV file and convert it to separate columns.
    
    Args:
        input_file (str): Path to the input CSV file
        output_file (str, optional): Path to the output CSV file. If None, will create a file
                                     with "_expanded" suffix in the same directory.
    
    Returns:
        str: Path to the created output file
    """
    print(f"Processing {input_file}...")
    
    # Check if the file is already an expanded file
    if "_expanded" in os.path.basename(input_file):
        print(f"Skipping already expanded file: {input_file}")
        return None
    
    # Read the CSV file
    try:
        df = pd.read_csv(input_file)
    except Exception as e:
        print(f"Error reading file {input_file}: {e}")
        return None
    
    # Get the last column name (assuming it contains the JSON data)
    last_column = df.columns[-1]
    print(f"Found JSON data in column: {last_column}")
    
    # Create a new dataframe to store the JSON data
    json_data = []
    error_rows = []
    
    # Extract JSON data from the last column
    for i, row in df.iterrows():
        try:
            # If the cell is empty or NaN, add an empty dictionary
            if pd.isna(row[last_column]) or row[last_column] == '':
                json_data.append({})
                continue
                
            # Handle numeric values
            if isinstance(row[last_column], (int, float)):
                json_data.append({})
                continue
                
            # Replace single quotes with double quotes and fix escaped quotes if necessary
            json_str = row[last_column].replace("'", '"')
            # Handle potential JSON formatting issues with booleans and null values
            json_str = json_str.replace('True', 'true').replace('False', 'false').replace('None', 'null')
            
            # Parse the JSON data
            data = json.loads(json_str)
            json_data.append(data)
        except Exception as e:
            print(f"Error parsing JSON data in row {i}: {e}")
            print(f"Problematic JSON string: {row[last_column]}")
            json_data.append({})
            error_rows.append(i)
    
    if error_rows:
        print(f"Warning: Could not parse JSON data in {len(error_rows)} rows: {error_rows}")
    
    # Convert the JSON data to a DataFrame with better handling of nested structures
    try:
        # Try to normalize the JSON data (flattens nested dictionaries)
        json_df = pd.json_normalize(json_data)
        
        # If the JSON data is empty, create an empty DataFrame with a dummy column
        if json_df.empty and json_data:
            json_df = pd.DataFrame([{}] * len(json_data))
    except Exception as e:
        print(f"Error converting JSON data to DataFrame: {e}")
        # Fallback to simple conversion for each key at the top level
        json_df = pd.DataFrame([{}] * len(df))
        
        # Try to extract top-level keys at least
        all_keys = set()
        for item in json_data:
            if isinstance(item, dict):
                all_keys.update(item.keys())
        
        for key in all_keys:
            try:
                json_df[key] = [item.get(key, None) if isinstance(item, dict) else None for item in json_data]
            except Exception as e:
                print(f"Could not extract key {key}: {e}")
    
    # Clean up column names by removing '%' characters
    json_df.columns = [col.replace('%', '') for col in json_df.columns]
    
    # Drop the original JSON column
    df_without_json = df.drop(columns=[last_column])
    
    # Concatenate the original DataFrame with the JSON DataFrame
    result_df = pd.concat([df_without_json, json_df], axis=1)
    
    # Generate the output file path if not provided
    if output_file is None:
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_expanded{input_path.suffix}"
    
    # Write the result to a new CSV file
    try:
        result_df.to_csv(output_file, index=False)
        print(f"Successfully created expanded CSV file: {output_file}")
        return output_file
    except Exception as e:
        print(f"Error writing to file {output_file}: {e}")
        return None

def process_latest_file():
    """Process the most recent CSV file in the output directory."""
    # Get the workspace directory
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(workspace_dir, "output")
    
    # Get all CSV files in the output directory
    csv_files = glob.glob(os.path.join(output_dir, "*.csv"))
    
    if not csv_files:
        print(f"No CSV files found in the output directory: {output_dir}")
        return
    
    # Filter out already expanded files
    non_expanded_files = [f for f in csv_files if "_expanded" not in os.path.basename(f)]
    
    if not non_expanded_files:
        print("All CSV files have already been expanded.")
        return
    
    # Find the most recent file
    latest_file = max(non_expanded_files, key=os.path.getmtime)
    print(f"Found latest file: {latest_file}")
    
    # Process the file
    extract_json_to_columns(latest_file)

def process_specific_file(file_path):
    """Process a specific CSV file."""
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}")
        return
    
    if not file_path.lower().endswith('.csv'):
        print(f"Not a CSV file: {file_path}")
        return
    
    extract_json_to_columns(file_path)

def main():
    """Main function to extract JSON data from CSV file."""
    # Parse command line arguments
    if len(sys.argv) > 1:
        if os.path.isfile(sys.argv[1]):
            # Process a specific file
            process_specific_file(sys.argv[1])
        elif sys.argv[1] == '--help' or sys.argv[1] == '-h':
            print("Usage:")
            print("  python json_extractor.py                    # Process the latest CSV file in the output directory")
            print("  python json_extractor.py <file_path>        # Process a specific CSV file")
            print("  python json_extractor.py --help             # Show this help message")
        else:
            print(f"Invalid argument: {sys.argv[1]}")
            print("Use --help for usage information")
    else:
        # Process the most recent file in the output directory
        process_latest_file()

if __name__ == "__main__":
    main() 