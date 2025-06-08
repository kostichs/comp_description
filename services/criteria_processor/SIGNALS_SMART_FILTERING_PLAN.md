# Smart Filtering Implementation Plan: Signals-Based Content Prioritization

## Overview
Implement intelligent content filtering that prioritizes scraped content based on Signals keywords from criteria files while preserving all information for comprehensive GPT analysis.

## Current State
- ✅ Scraping 3 out of 10 Serper results with ScrapingBee
- ✅ Basic content aggregation for GPT analysis
- ✅ Signals column exists in criteria files but not utilized

## Implementation Plan

### Phase 1: Configuration and Setup
- [x] **1.1** Update `SCRAPE_TOP_N_RESULTS` from 3 to 10 in config
- [ ] **1.2** Add new configuration variables for smart filtering
- [ ] **1.3** Create Signals extraction utility functions
- [ ] **1.4** Add content structure templates

### Phase 2: Signals Processing
- [ ] **2.1** Create `extract_signals_keywords()` function
  - Parse Signals column from criteria
  - Handle comma-separated keywords
  - Clean and normalize keywords
- [ ] **2.2** Create `find_signal_matches()` function
  - Case-insensitive keyword matching
  - Support for phrase matching (quoted strings)
  - Context extraction around matches

### Phase 3: Content Structure Enhancement
- [ ] **3.1** Modify `scrape_website_text()` to return structured content
  - Original full content
  - Metadata (URL, title, word count)
  - Content sections identification
- [ ] **3.2** Implement DOM-based filtering
  - Remove navigation elements
  - Remove footer content
  - Extract main content areas

### Phase 4: Smart Content Prioritization
- [ ] **4.1** Create `prioritize_content()` function
  - Extract paragraphs containing Signals keywords
  - Maintain surrounding context (±1-2 sentences)
  - Rank by keyword density and relevance
- [ ] **4.2** Implement content structuring
  - Priority content section (with Signals)
  - Full content section (complete scraped data)
  - Clear section headers for GPT

### Phase 5: Integration with Existing Pipeline
- [ ] **5.1** Update `process_company_deep_analysis()` function
  - Integrate new scraping count (10 results)
  - Add Signals-based prioritization
  - Maintain backward compatibility
- [ ] **5.2** Modify GPT analysis prompt structure
  - Guide GPT attention to priority content first
  - Ensure full content remains accessible
  - Update prompt templates

### Phase 6: ScrapingBee Integration Updates
- [ ] **6.1** Update ScrapingBee client to handle increased load
  - Optimize for 10 concurrent requests
  - Add retry logic for failed scrapes
  - Improve error handling
- [ ] **6.2** Enhance logging for new pipeline
  - Log Signals extraction results
  - Track priority vs full content ratios
  - Monitor context window usage

### Phase 7: Testing and Validation
- [ ] **7.1** Create test cases for Signals extraction
  - Test with real criteria files
  - Validate keyword matching accuracy
  - Test edge cases (empty signals, special characters)
- [ ] **7.2** Validate content prioritization
  - Compare priority vs full content
  - Ensure no information loss
  - Test with various website structures
- [ ] **7.3** End-to-end testing
  - Run full analysis with new pipeline
  - Compare results with previous version
  - Validate GPT analysis quality

### Phase 8: Performance Optimization
- [ ] **8.1** Monitor context window usage
  - Track token counts per analysis
  - Optimize content structure
  - Add dynamic content trimming if needed
- [ ] **8.2** Optimize processing speed
  - Parallel scraping implementation
  - Efficient text processing
  - Cache frequently used patterns

## Success Criteria
- [ ] All 10 Serper results are scraped successfully
- [ ] Signals keywords properly extracted and utilized
- [ ] Priority content clearly separated and highlighted
- [ ] Full content preserved for comprehensive analysis
- [ ] GPT analysis quality maintained or improved
- [ ] No significant performance degradation
- [ ] Context window limits respected

## Risk Mitigation
- [ ] **Context Window Overflow**: Implement dynamic content trimming
- [ ] **Performance Issues**: Add parallel processing and caching
- [ ] **Signals Parsing Errors**: Robust error handling and fallbacks
- [ ] **Quality Regression**: A/B testing framework for comparison

## Files to Modify
- `src/utils/config.py` - Update scraping configuration
- `src/external/scrapingbee_client.py` - Enhanced scraping logic
- `src/analysis/deep_analysis.py` - Smart filtering implementation
- `src/llm/gpt_analyzer.py` - Prompt structure updates
- `src/utils/signals_processor.py` - New utility module

## Next Steps
Start with Phase 1.1: Update SCRAPE_TOP_N_RESULTS configuration. 