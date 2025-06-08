"""
Utility module for processing Signals keywords from criteria files
"""

import re
import pandas as pd
from typing import List, Dict, Tuple, Optional
from src.utils.logging import log_debug, log_info
from src.utils.config import SMART_FILTERING_CONFIG


def extract_signals_keywords(criterion: pd.Series) -> List[str]:
    """
    Extract and clean keywords from the Signals column of a criterion.
    
    Args:
        criterion (pd.Series): A row from criteria DataFrame
        
    Returns:
        List[str]: List of cleaned keywords
    """
    signals_text = criterion.get('Signals', '')
    
    if pd.isna(signals_text) or not signals_text or str(signals_text).strip() == '':
        log_debug(f"No signals found for criterion: {criterion.get('Criteria', 'Unknown')}")
        return []
    
    signals_text = str(signals_text).strip()
    
    # Handle quoted phrases (e.g., "API documentation", "enterprise solutions")
    quoted_phrases = re.findall(r'"([^"]+)"', signals_text)
    
    # Remove quoted phrases from text to avoid double processing
    text_without_quotes = re.sub(r'"[^"]+"', '', signals_text)
    
    # Split remaining text by common separators
    individual_keywords = re.split(r'[,;|]', text_without_quotes)
    
    # Clean and combine all keywords
    all_keywords = []
    
    # Add quoted phrases (preserve as complete phrases)
    for phrase in quoted_phrases:
        phrase = phrase.strip()
        if phrase:
            all_keywords.append(phrase)
    
    # Add individual keywords
    for keyword in individual_keywords:
        keyword = keyword.strip()
        if keyword and keyword not in ['', 'N/A', 'n/a', 'None']:
            all_keywords.append(keyword)
    
    # Remove duplicates while preserving order
    unique_keywords = []
    for kw in all_keywords:
        if kw not in unique_keywords:
            unique_keywords.append(kw)
    
    log_debug(f"Extracted {len(unique_keywords)} signals keywords: {unique_keywords}")
    return unique_keywords


def find_signal_matches(content: str, signals_keywords: List[str]) -> List[Dict[str, any]]:
    """
    Find paragraphs and sentences containing signals keywords.
    
    Args:
        content (str): The scraped content to search
        signals_keywords (List[str]): Keywords to search for
        
    Returns:
        List[Dict]: List of matches with context information
    """
    if not content or not signals_keywords:
        return []
    
    matches = []
    case_sensitive = SMART_FILTERING_CONFIG['case_sensitive_matching']
    context_sentences = SMART_FILTERING_CONFIG['context_sentences_around_match']
    
    # Split content into sentences
    sentences = re.split(r'[.!?]+', content)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    for i, sentence in enumerate(sentences):
        sentence_matches = []
        search_text = sentence if case_sensitive else sentence.lower()
        
        for keyword in signals_keywords:
            search_keyword = keyword if case_sensitive else keyword.lower()
            
            # Check for keyword match
            if search_keyword in search_text:
                sentence_matches.append(keyword)
        
        if sentence_matches:
            # Extract context around the match
            start_idx = max(0, i - context_sentences)
            end_idx = min(len(sentences), i + context_sentences + 1)
            context = '. '.join(sentences[start_idx:end_idx])
            
            match_info = {
                'sentence_index': i,
                'matched_keywords': sentence_matches,
                'sentence': sentence,
                'context': context,
                'keyword_count': len(sentence_matches),
                'sentence_length': len(sentence)
            }
            matches.append(match_info)
    
    # Sort by keyword count (descending) and sentence length (descending)
    matches.sort(key=lambda x: (x['keyword_count'], x['sentence_length']), reverse=True)
    
    log_debug(f"Found {len(matches)} signal matches in content")
    return matches


def prioritize_content(scraped_content: str, signals_keywords: List[str]) -> Tuple[str, str]:
    """
    Prioritize content based on signals keywords while preserving all information.
    
    Args:
        scraped_content (str): The full scraped content
        signals_keywords (List[str]): Keywords to prioritize
        
    Returns:
        Tuple[str, str]: (priority_content, full_structured_content)
    """
    if not scraped_content:
        return "", ""
    
    if not signals_keywords or not SMART_FILTERING_CONFIG['enable_signals_prioritization']:
        # If no signals or prioritization disabled, return original content
        header = SMART_FILTERING_CONFIG['full_content_header']
        return "", f"{header}\n{scraped_content}"
    
    # Find matches
    matches = find_signal_matches(scraped_content, signals_keywords)
    
    if not matches:
        # No matches found, return original structure
        header = SMART_FILTERING_CONFIG['full_content_header']
        return "", f"{header}\n{scraped_content}"
    
    # Extract priority content from matches
    priority_parts = []
    used_sentences = set()
    
    for match in matches:
        sentence_idx = match['sentence_index']
        if sentence_idx not in used_sentences:
            priority_parts.append(match['context'])
            # Mark sentences in this context as used
            context_sentences = re.split(r'[.!?]+', match['context'])
            for j, _ in enumerate(context_sentences):
                used_sentences.add(sentence_idx - SMART_FILTERING_CONFIG['context_sentences_around_match'] + j)
    
    priority_content = '\n\n'.join(priority_parts)
    
    # Check minimum length requirement
    min_length = SMART_FILTERING_CONFIG['min_priority_content_length']
    if len(priority_content) < min_length:
        log_debug(f"Priority content too short ({len(priority_content)} < {min_length}), using full content")
        header = SMART_FILTERING_CONFIG['full_content_header']
        return "", f"{header}\n{scraped_content}"
    
    # Check maximum ratio
    max_ratio = SMART_FILTERING_CONFIG['max_priority_content_ratio']
    if len(priority_content) > len(scraped_content) * max_ratio:
        # Trim priority content if it's too large
        priority_content = priority_content[:int(len(scraped_content) * max_ratio)]
        priority_content += "\n[... content trimmed to maintain ratio ...]"
    
    # Structure the final content
    priority_header = SMART_FILTERING_CONFIG['priority_section_header']
    full_header = SMART_FILTERING_CONFIG['full_content_header']
    
    structured_content = f"{priority_header}\n{priority_content}\n\n{full_header}\n{scraped_content}"
    
    log_info(f"Created priority content: {len(priority_content)} chars from {len(signals_keywords)} signals")
    return priority_content, structured_content


def clean_scraped_content(content: str) -> str:
    """
    Clean scraped content by removing navigation, footer, and other non-essential elements.
    
    Args:
        content (str): Raw scraped content
        
    Returns:
        str: Cleaned content
    """
    if not content:
        return ""
    
    # Remove common navigation and footer patterns
    patterns_to_remove = [
        r'©\s*\d{4}.*?rights reserved',  # Copyright notices
        r'privacy policy.*?terms of service',  # Legal links
        r'follow us on.*?social media',  # Social media links
        r'subscribe to.*?newsletter',  # Newsletter signup
        r'cookie.*?policy',  # Cookie policies
        r'home\s+about\s+services\s+contact',  # Navigation menus
    ]
    
    cleaned_content = content
    for pattern in patterns_to_remove:
        cleaned_content = re.sub(pattern, '', cleaned_content, flags=re.IGNORECASE | re.DOTALL)
    
    # Remove excessive whitespace
    cleaned_content = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_content)
    cleaned_content = re.sub(r' +', ' ', cleaned_content)
    
    return cleaned_content.strip()


def extract_content_metadata(url: str, content: str) -> Dict[str, any]:
    """
    Extract metadata from scraped content.
    
    Args:
        url (str): The source URL
        content (str): The scraped content
        
    Returns:
        Dict: Metadata dictionary
    """
    word_count = len(content.split()) if content else 0
    char_count = len(content) if content else 0
    
    # Extract title from content (basic heuristic)
    title_match = re.search(r'^(.+?)(?:\n|$)', content.strip()) if content else None
    title = title_match.group(1)[:100] if title_match else "No title found"
    
    return {
        'url': url,
        'title': title,
        'word_count': word_count,
        'char_count': char_count,
        'has_content': bool(content and content.strip())
    } 