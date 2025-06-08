# Signals Smart Filtering Implementation Plan

## Overview
Implement smart content filtering using Signals keywords from criteria files to improve analysis quality while preserving all information through prioritization rather than filtering.

## Implementation Status

### ✅ Phase 1: Configuration and Setup (COMPLETED)
**Status: COMPLETED** ✅

#### 1.1: Update scraping configuration ✅
- Updated `SCRAPE_TOP_N_RESULTS` from 3 to 10 in `config.py`
- All 10 Serper results will now be scraped for maximum information

#### 1.2: Add smart filtering configuration ✅
- Added `SMART_FILTERING_CONFIG` dictionary with:
  - `enable_signals_prioritization: True`
  - Content structure headers for priority and full content sections
  - Prioritization parameters (min length, max ratio, context sentences)
  - Case sensitivity and matching options

#### 1.3: Create Signals extraction utility functions ✅
- Created `src/utils/signals_processor.py` with comprehensive functions:
  - `extract_signals_keywords()`: Parse and clean Signals column keywords
  - `find_signal_matches()`: Find content containing signals keywords
  - `prioritize_content()`: Structure content with priority sections
  - `clean_scraped_content()`: Remove navigation/footer elements
  - `extract_content_metadata()`: Extract metadata from scraped content

### ✅ Phase 2: Enhanced ScrapingBee Integration (COMPLETED)
**Status: COMPLETED** ✅

#### 2.1: Update individual scraping function ✅
- Enhanced `scrape_website_text()` to accept criterion parameter
- Added signals-based smart filtering to individual URL scraping
- Integrated content cleaning and prioritization

#### 2.2: Create batch scraping function ✅
- Added `scrape_multiple_urls_with_signals()` for processing multiple URLs
- Aggregates content from all 10 URLs with signals prioritization
- Creates structured output with priority and full content sections
- Includes scraping summary with metadata

### ✅ Phase 3: GPTAnalyzer Integration (COMPLETED)
**Status: COMPLETED** ✅

#### 3.1: Update dynamic criterion processing ✅
- Modified `_process_dynamic_criterion()` to use new batch scraping
- Enhanced GPT prompts with signals context
- Added signals keywords to analysis instructions

#### 3.2: Enhance prompt generation ✅
- Prompts now include "Key signals to look for" section
- GPT receives explicit instruction to pay attention to signals keywords
- Maintains backward compatibility for criteria without signals

### ✅ Phase 4: Testing and Validation (COMPLETED)
**Status: COMPLETED** ✅

#### 4.1: Unit tests ✅
- Verified signals keyword extraction from various formats
- Tested content matching and prioritization logic
- Confirmed configuration values are properly set

#### 4.2: Integration tests ✅
- Validated GPTAnalyzer integration with signals processing
- Tested prompt enhancement with signals context
- Verified import compatibility and function availability

## Implementation Details

### Key Features Implemented:
1. **10 URL Scraping**: Increased from 3 to 10 URLs per criterion for comprehensive coverage
2. **Signals Processing**: Extract keywords from Signals column (handles quoted phrases, separators)
3. **Smart Prioritization**: Structure content with priority sections while preserving all information
4. **Enhanced Prompts**: GPT receives signals context for better analysis focus
5. **Batch Processing**: Efficient aggregation of multiple URL content with signals awareness

### Architecture Changes:
- **New Module**: `src/utils/signals_processor.py` for all signals-related functionality
- **Enhanced ScrapingBee**: Signals-aware scraping with content structuring
- **Updated GPTAnalyzer**: Integrated signals processing into analysis workflow
- **Configuration**: Centralized smart filtering settings in config

### Content Structure:
```
=== PRIORITY CONTENT (Contains signals keywords) ===
[Relevant content containing signals keywords with context]

=== FULL SCRAPED CONTENT ===
[Complete scraped content from all URLs]

=== Scraping Summary ===
[Metadata about URLs processed and signals used]
```

## Remaining Phases

### Phase 5: Real-world Testing (PENDING)
- [ ] Test with actual companies and criteria files
- [ ] Monitor ScrapingBee API usage and costs
- [ ] Validate analysis quality improvements
- [ ] Performance optimization if needed

### Phase 6: Monitoring and Optimization (PENDING)
- [ ] Add metrics for signals effectiveness
- [ ] Monitor content prioritization ratios
- [ ] Optimize signals keyword matching
- [ ] Fine-tune prioritization parameters

### Phase 7: Documentation and Training (PENDING)
- [ ] Update user documentation
- [ ] Create signals keyword guidelines
- [ ] Document best practices for criteria creation

## Next Steps
1. **Deploy and Test**: Use the enhanced system with real company analysis
2. **Monitor Performance**: Track ScrapingBee usage and analysis quality
3. **Iterate**: Refine signals processing based on real-world results

## Technical Notes
- **Backward Compatibility**: System works with existing criteria files (signals optional)
- **Graceful Degradation**: Falls back to standard processing if signals unavailable
- **Configurable**: All smart filtering features can be enabled/disabled via config
- **Preserves Information**: Never loses content through summarization, only prioritizes 