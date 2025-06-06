# To-Do List: Multiple Criteria Files Processing

1. **Config File Enhancement**
   - [ ] Modify `CRITERIA_TYPE` in config.py to accept a comma-separated list.
   - [ ] Update `CRITERIA_PATH` to be generated based on each criteria type.
   - [ ] Update `validate_config()` to validate each criteria file.

2. **Data Loading Enhancement**
   - [ ] Update `load_data()` in data_utils.py to load multiple criteria files.
   - [ ] Modify the return structure to include data for each criteria type.

3. **Processing Logic Enhancement**
   - [ ] Update the main processing loop in main.py to handle multiple criteria types.
   - [ ] Add sequential processing for each criteria type.
   - [ ] Ensure each criteria type's results are stored separately.

4. **Output Format Enhancement**
   - [ ] Update `save_results()` in data_utils.py to generate separate columns for each criteria type.
   - [ ] Ensure each column is named according to its criteria type.

5. **Testing**
   - [ ] Test with a single criteria type to ensure backwards compatibility.
   - [ ] Test with multiple criteria types to verify new functionality.
   - [ ] Verify output format with multiple criteria columns.

6. **Documentation**
   - [ ] Update README.md with information about the new feature.
   - [ ] Add examples of how to specify multiple criteria types.

7. **Error Handling**
   - [ ] Add error handling for missing criteria files.
   - [ ] Add validation for the comma-separated list format. 