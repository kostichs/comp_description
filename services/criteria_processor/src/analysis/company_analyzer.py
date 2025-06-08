import json
from typing import Dict, List
import pandas as pd
from src.external.serper import serper_search, save_serper_result
from src.llm.gpt_analyzer import GPTAnalyzer
from src.llm.query_builder import QueryBuilder
from src.utils.logging import log_info, log_error, log_debug
from src.analysis.deep_analysis import process_company_deep_analysis

class CompanyAnalyzer:
    """
    Класс для полного анализа одной компании.
    """
    def __init__(self, criteria_df: pd.DataFrame, gpt_analyzer: GPTAnalyzer, query_builder: QueryBuilder):
        self.criteria_df = criteria_df
        self.gpt_analyzer = gpt_analyzer
        self.query_builder = query_builder

    def analyze(self, company_name: str, company_description: str, session_id: str, use_deep_analysis: bool = False) -> Dict:
        """
        Анализирует одну компанию: строит запрос, ищет в Serper, анализирует с помощью GPT.
        """
        log_info(f"Analyzing company: {company_name}")
        
        query = self.query_builder.build_query(company_name, company_description)
        log_debug(f"🔎 Serper query: {query}")
        
        try:
            search_results = serper_search(query)
            if session_id:
                save_serper_result(session_id, company_name, query, search_results)
            
            scraped_text_all = ""
            if use_deep_analysis and search_results:
                log_info(f"Performing deep analysis for {company_name}...")
                scraped_text_all = process_company_deep_analysis(
                    company_name, 
                    search_results, 
                    session_id,
                    query
                )
        
            analysis_context = self.build_analysis_context(
                company_name=company_name,
                company_description=company_description,
                search_results=search_results,
                scraped_text=scraped_text_all
            )
            
            analysis_result = self.gpt_analyzer.analyze_criteria(analysis_context, self.criteria_df)
            
            final_result = {
                "Company": company_name,
                "Description": company_description,
                **analysis_result,
                "Serper_Query": query,
                "All_Results": json.dumps(search_results, ensure_ascii=False) if search_results else None,
                "Deep_Analysis_Summary": scraped_text_all[:500] + "..." if scraped_text_all else "Not performed"
            }
            
            return final_result

        except Exception as e:
            log_error(f"An error occurred during analysis for {company_name}: {e}")
            return {
                "Company": company_name,
                "Description": company_description,
                "error": str(e)
            }

    def build_analysis_context(self, company_name: str, company_description: str, search_results: List[Dict], scraped_text: str) -> str:
        """
        Собирает весь текст для анализа в единый контекст.
        """
        context_parts = []
        context_parts.append(f"Company: {company_name}")
        if company_description:
            context_parts.append(f"Description: {company_description}")
        
        if search_results:
            context_parts.append("\\n--- Search Results ---")
            for item in search_results:
                context_parts.append(f"Title: {item.get('title', 'N/A')}")
                context_parts.append(f"Link: {item.get('link', 'N/A')}")
                context_parts.append(f"Snippet: {item.get('snippet', 'N/A')}")
        
        if scraped_text:
            context_parts.append("\\n--- Scraped Website Content ---")
            context_parts.append(scraped_text)
            
        return "\\n".join(context_parts) 