# Product Requirements Document: Multiple Criteria Files Processing

## Overview
Currently, the system processes a single criteria file specified in the config file. The enhancement will allow multiple criteria files to be processed sequentially, with each criteria file resulting in a separate column in the output.

## Requirements

1. **Config File Enhancement**
   - Modify the config file to accept a comma-separated list of criteria types (e.g., "VM,CDN,CDN2") instead of a single criteria type.

2. **Data Loading Enhancement**
   - Update the data loading process to handle multiple criteria files.
   - Each criteria file should be loaded separately based on its type.

3. **Processing Logic Enhancement**
   - Process each criteria file sequentially.
   - For each criteria file, create a separate column in the output with the corresponding criteria type.

4. **Output Format Enhancement**
   - Update the output format to include separate columns for each criteria type.
   - Each column should contain the criteria checking results for the corresponding criteria type.

5. **Error Handling**
   - Add error handling for cases where a specified criteria file does not exist.
   - Add validation to ensure that at least one valid criteria type is provided.

## Technical Specifications

1. **Config File Changes**
   - Change `CRITERIA_TYPE` in config.py to accept a comma-separated list.
   - Update `CRITERIA_PATH` to be generated based on each criteria type.

2. **Data Loading Changes**
   - Modify `load_data()` in data_utils.py to load multiple criteria files.
   - Return a dictionary with criteria data for each type.

3. **Processing Logic Changes**
   - Update main.py to process each criteria type sequentially.
   - Add a loop to process each criteria type for each company.

4. **Output Format Changes**
   - Update `save_results()` in data_utils.py to include separate columns for each criteria type. 