# Company Name Resolution Feature

## Overview

The Company Name Resolution feature addresses the challenge of processing various types of input data that may not directly represent the actual operating company name. This includes:

- **Juridical/Legal Names**: "Shanghai Perfect Technology Co., Ltd.", "HOSTY, UAB"
- **Founder/CEO Names**: "Elon Musk", "Bill Gates"
- **Email Addresses**: "contact@tesla.com", "info@microsoft.com"
- **Organization Registration Names**: Legal entity names that differ from brand names
- **Generic Terms**: "remote work", "job opportunities" (these are filtered out)

## Problem Statement

When processing company data, you may encounter:

1. **Juridical Names**: Legal entity names that include suffixes like "Co., Ltd.", "Inc.", "LLC", "UAB", "GmbH"
2. **Indirect References**: Founder names, email addresses, or other identifiers that don't directly specify the company
3. **Ambiguous Input**: Data that could refer to multiple companies or no specific company at all

The standard pipeline expects actual company names, so these inputs can lead to poor search results or failed processing.

## Solution Architecture

### 1. Configuration File: `llm_company_resolution_config.yaml`

Controls when and how company name resolution is triggered:

```yaml
integration:
  enable_resolution_stage: false  # Set to true to enable
  
  trigger_conditions:
    - "contains_juridical_suffixes"
    - "contains_email_pattern" 
    - "contains_person_indicators"
    - "low_company_validation_score"
  
  juridical_suffixes:
    - "Co., Ltd."
    - ", Inc."
    - ", LLC"
    - "UAB"
    - "GmbH"
    # ... more suffixes
```

### 2. Resolution Module: `src/company_name_resolver.py`

Handles the actual resolution process using **search-enabled LLM** to:
- Perform real-time web searches for unknown inputs
- Identify the input type (juridical name, founder name, email, etc.)
- Extract or identify the actual operating company name through search
- Provide confidence levels and reasoning based on search results
- Determine if processing should continue

### 3. Integration with Main Pipeline

The resolution stage runs **before** the main processing pipeline:

```
Input → Name Resolution → Validation → Main Pipeline → Output
```

## Usage

### Enabling Resolution

1. **Edit Configuration**:
   ```yaml
   # In llm_company_resolution_config.yaml
   integration:
     enable_resolution_stage: true
   ```

2. **The system will automatically**:
   - Detect trigger conditions in input data
   - Attempt to resolve company names using LLM
   - Continue with resolved names or original input based on confidence

### Input Examples and Expected Behavior

| Input Type | Example | Expected Resolution | Confidence |
|------------|---------|-------------------|------------|
| Juridical Name | "Shanghai Perfect Technology Co., Ltd." | "Shanghai Perfect Technology" (via search) | High |
| Founder Name | "Elon Musk" | "Tesla" or "SpaceX" (via search) | Medium-High |
| Email | "contact@tesla.com" | "Tesla" (via domain search) | Medium |
| Unknown Email | "dshfakljsdhfk@gmail.com" | Search for email → Find company if exists | Low-Medium |
| Generic Term | "remote work" | Skip processing (no search results) | N/A |

### Output Structure

When resolution is used, the output includes additional fields:

```json
{
  "Company_Name": "Shanghai Perfect Technology Co., Ltd.",  // Original input
  "Resolved_Company_Name": "Shanghai Perfect Technology",   // Resolved name
  "resolution_metadata": {
    "resolution_used": true,
    "trigger_reason": "contains_juridical_suffix: Co., Ltd.",
    "resolution_result": {
      "identified_company_name": "Shanghai Perfect Technology",
      "confidence_level": "high",
      "input_type": "juridical_name",
      "reasoning": "Found through web search: company operates as Shanghai Perfect Technology",
      "search_summary": "Search confirmed company exists with official website",
      "company_website": "https://shanghaiperfect.com",
      "should_proceed": true
    }
  }
}
```

## Configuration Options

### Resolution Model Settings

```yaml
resolution_model: "gpt-4o-search-preview"  # Search-enabled model for real-time lookup
# resolution_temperature: 0.1  # Temperature not used with search models
```

### Validation Rules

```yaml
validation_rules:
  min_confidence_to_proceed: "medium"  # minimum confidence to proceed
  require_company_name: true
  max_alternative_terms: 5
```

### Fallback Strategies

```yaml
fallback_strategies:
  - "use_original_input"  # Use original input as company name
  - "skip_processing"     # Skip this entry entirely
  - "manual_review"       # Flag for manual review
```

## Testing

Run the test suite to verify functionality:

```bash
python test_company_resolution.py
```

This will test:
- Trigger condition detection
- Resolution functionality (if enabled and API key provided)
- Integration with main pipeline

## Search Capabilities

The resolution system now uses **search-enabled LLM** (`gpt-4o-search-preview`) which can:

1. **Search for unknown emails**: Find company associations for any email address
2. **Look up people**: Search for founders, CEOs, and their current companies
3. **Verify juridical names**: Confirm company existence and find operating names
4. **Domain research**: Investigate company domains and websites
5. **Real-time data**: Access current information, not just training data

### Search Examples

- `dshfakljsdhfk@gmail.com` → Searches web → Finds if this email is associated with any company
- `John Smith CEO` → Searches → Finds current company association
- `Obscure Company Ltd.` → Searches → Verifies existence and finds real brand name

## Performance Considerations

1. **API Costs**: Each resolution requires a search-enabled LLM API call (more expensive than regular LLM)
2. **Processing Time**: Adds ~3-5 seconds per resolved entry (due to web search)
3. **Accuracy**: Much higher accuracy due to real-time web search capabilities
4. **Rate Limits**: Search models may have different rate limits

## Best Practices

1. **Enable Selectively**: Only enable resolution when you expect juridical names or indirect references
2. **Monitor Confidence**: Review low-confidence resolutions manually
3. **Validate Results**: Check resolved names make sense for your use case
4. **Batch Processing**: Consider processing in smaller batches when resolution is enabled

## Troubleshooting

### Common Issues

1. **Resolution Not Triggering**:
   - Check if `enable_resolution_stage: true` in config
   - Verify input matches trigger conditions
   - Check logs for trigger detection

2. **Low Confidence Results**:
   - Review and adjust `min_confidence_to_proceed` setting
   - Consider manual review for ambiguous cases
   - Update trigger conditions if needed

3. **API Errors**:
   - Verify OpenAI API key is valid
   - Check rate limits and quotas
   - Review error logs for specific issues

### Logging

Enable detailed logging in the configuration:

```yaml
logging:
  log_resolution_attempts: true
  log_confidence_scores: true
  log_failed_resolutions: true
```

## Future Enhancements

Potential improvements:
- Caching of resolution results
- Multiple LLM model support
- Custom resolution rules per industry
- Batch resolution for efficiency
- Integration with external company databases 