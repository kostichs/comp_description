### This script converts a CSV file from semicolon delimiter to comma delimiter.
### It also moves the original file to a directory called "OLD_CODE" with "_semicolon" suffix.
### It tries different encodings and properly handles quoting of fields containing commas.

import csv
import os
import sys
import shutil
from pathlib import Path
import re

def fix_cdn_file():
    """
    Specifically fix the CDN criteria file to match VM file format
    """
    input_file = "input/CDN_Target Audience Criteria.csv"
    temp_output_file = "input/CDN_Target Audience Criteria_temp.csv"
    
    # Create OLD_CODE directory if it doesn't exist
    old_code_dir = Path("OLD_CODE")
    old_code_dir.mkdir(exist_ok=True)
    
    # Set backup path for original file
    backup_file = old_code_dir / "CDN_Target Audience Criteria_backup.csv"
    
    # Read the original content
    with open(input_file, 'r', encoding='latin1') as file:
        content = file.read()
    
    # Fix common encoding issues
    # Remove double quotes at start and end of each line
    content = re.sub(r'^"', '', content, flags=re.MULTILINE)
    content = re.sub(r'"$', '', content, flags=re.MULTILINE)
    
    # Fix the header
    content = content.replace('Product,Target Audience,Criteria Type,Criteria', 
                             'Product,Target Audience,Criteria Type,Criteria')
    
    # Write the corrected content with proper quoting
    with open(temp_output_file, 'w', encoding='utf-8') as file:
        file.write(content)
    
    # Read the temp file as CSV and write properly formatted output
    with open(temp_output_file, 'r', encoding='utf-8') as infile:
        reader = csv.reader(infile)
        rows = list(reader)
    
    with open(input_file + ".new", 'w', encoding='utf-8', newline='') as outfile:
        writer = csv.writer(outfile, quoting=csv.QUOTE_MINIMAL)
        for row in rows:
            writer.writerow(row)
    
    # Backup original file
    shutil.copy(input_file, backup_file)
    
    # Replace original with fixed file
    shutil.move(input_file + ".new", input_file)
    
    # Clean up temp file
    if os.path.exists(temp_output_file):
        os.remove(temp_output_file)
    
    print(f"Fixed CDN file to match VM format. Original backed up to {backup_file}")


def convert_csv_delimiter(input_file):
    """
    Convert a CSV file from semicolon delimiter to comma delimiter.
    Properly handles quoting of fields containing commas.
    Original file is moved to OLD_CODE directory with "_semicolon" suffix.
    
    Args:
        input_file: Path to the input file with semicolon delimiter
    """
    input_path = Path(input_file)
    temp_output_file = str(input_path.with_stem(f"{input_path.stem}_temp"))
    
    # Create OLD_CODE directory if it doesn't exist
    old_code_dir = Path("OLD_CODE")
    old_code_dir.mkdir(exist_ok=True)
    
    # Set backup path for original file
    backup_file = old_code_dir / f"{input_path.stem}_semicolon{input_path.suffix}"
    
    # Try different encodings
    encodings = ['utf-8', 'utf-8-sig', 'latin1', 'cp1251', 'cp1252', 'iso-8859-1']
    
    for encoding in encodings:
        try:
            with open(input_file, 'r', newline='', encoding=encoding) as infile:
                reader = csv.reader(infile, delimiter=';')
                
                with open(temp_output_file, 'w', newline='', encoding='utf-8') as outfile:
                    writer = csv.writer(outfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
                    for row in reader:
                        writer.writerow(row)
            
            # Move original file to OLD_CODE directory
            shutil.move(input_file, backup_file)
            
            # Rename temp file to original filename
            shutil.move(temp_output_file, input_file)
            
            print(f"Converted {input_file} (original moved to {backup_file}) using {encoding} encoding")
            return
        except UnicodeDecodeError:
            continue
    
    print(f"Failed to convert {input_file}. Tried encodings: {', '.join(encodings)}")

def main():
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] == "cdn"):
        # If no arguments or "cdn" is specified, fix the CDN file
        fix_cdn_file()
        return
        
    for file_path in sys.argv[1:]:
        if os.path.isfile(file_path):
            convert_csv_delimiter(file_path)
        else:
            print(f"File not found: {file_path}")

if __name__ == "__main__":
    main() 