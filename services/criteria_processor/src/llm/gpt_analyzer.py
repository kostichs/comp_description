import pandas as pd
import openai
from openai import OpenAI
import re
from src.utils.logging import log_info, log_debug, log_error
from src.external.serper import perform_google_search, save_serper_result, format_search_query
from src.external.scrapingbee_client import scrape_website_text, scrape_multiple_urls_with_signals
from src.external.async_scrapingbee import run_async_scrape_sync
from src.utils.signals_processor import extract_signals_keywords
from src.utils.config import ASYNC_SCRAPING_CONFIG
from typing import Tuple

class GPTAnalyzer:
    """
    Класс для анализа данных с помощью GPT.
    """
    def __init__(self, session_id: str = None):
        self.client = OpenAI()
        self.session_id = session_id

    def analyze_criteria(self, context: str, criteria_df: pd.DataFrame, website: str = None) -> dict:
        """
        Итеративно проверяет соответствие компании критериям по разным продуктам и аудиториям.
        """
        self.website = website  # Store for use in _process_dynamic_criterion
        results = {}
        # Группируем критерии по продуктам
        for product, product_group in criteria_df.groupby('Product'):
            results[product] = self._evaluate_product(product, product_group, context)
        return self._format_results(results)

    def _evaluate_product(self, product_name: str, product_df: pd.DataFrame, context: str) -> list:
        """Оценивает соответствие по всем целевым аудиториям одного продукта."""
        log_info(f"Проверяем продукт: {product_name}")
        audience_results = []
        # Группируем по целевым аудиториям
        for audience, audience_group in product_df.groupby('Target Audience'):
            audience_results.append(self._evaluate_audience(audience, audience_group, context, product_name))
        return audience_results

    def _evaluate_audience(self, audience_name: str, audience_df: pd.DataFrame, context: str, product_name: str) -> dict:
        """Оценивает соответствие по всем критериям для одной целевой аудитории."""
        company_name_match = re.search(r"Company: (.*?)\\n", context)
        company_name = company_name_match.group(1) if company_name_match else "Unknown Company"
        
        log_info(f"Проверяем {product_name} -> {audience_name}")

        # Шаг 1: Проверка обязательных критериев
        mandatory_criteria = audience_df[audience_df['Criteria Type'] == 'Mandatory']
        mandatory_passed = True
        for _, criterion in mandatory_criteria.iterrows():
            passed, _, _ = self._process_dynamic_criterion(company_name, criterion, context)
            if not passed:
                mandatory_passed = False
                break
        
        if not mandatory_passed:
            log_info(f"Mandatory НЕ пройдены для {product_name} -> {audience_name}")
            return {"Target Audience": audience_name, "Qualified": False, "Reason": "Mandatory criteria failed", "Score": 0}

        log_info(f"Mandatory пройдены для {product_name} -> {audience_name}")

        # Шаг 2: Оценка квалификационных критериев
        qualification_criteria = audience_df[audience_df['Criteria Type'] == 'Qualification']
        if qualification_criteria.empty:
            return {"Target Audience": audience_name, "Qualified": True, "Reason": "No qualification criteria", "Score": 1}

        total_score = 0
        max_score = len(qualification_criteria)
        
        for _, criterion in qualification_criteria.iterrows():
            passed, reason, _ = self._process_dynamic_criterion(company_name, criterion, context)
            if passed:
                total_score += 1
        
        final_score = total_score / max_score if max_score > 0 else 0
        qualified = final_score > 0.5

        reason = f"{total_score}/{max_score} qualification criteria passed."
        log_info(f"{'Квалифицирована' if qualified else 'НЕ квалифицирована'}: {product_name} -> {audience_name} (Score: {final_score:.3f})")

        return {"Target Audience": audience_name, "Qualified": qualified, "Reason": reason, "Score": final_score}

    def _process_dynamic_criterion(self, company_name: str, criterion: pd.Series, context: str) -> Tuple[bool, str, str]:
        """Обрабатывает один критерий, выполняя поиск и анализ если необходимо."""
        criterion_text = criterion['Criteria']
        full_context = context

        if pd.notna(criterion.get('Search Query')):
            search_query_template = str(criterion['Search Query'])
            
            # Handle both {website} and {company_name} placeholders
            search_query = search_query_template
            
            # First replace {website} if present and available
            if '{website}' in search_query:
                if self.website:
                    search_query = format_search_query(search_query, self.website)
                else:
                    log_debug(f"⚠️ Warning: Search query contains {{website}} but no website provided")
                    # Skip this criterion if website is required but not available
                    return False, "No website provided for site: search", ""
            
            # Then replace {company_name} if present
            if '{company_name}' in search_query:
                search_query = search_query.replace('{company_name}', company_name)
            
            log_debug(f"Выполняем динамический поиск: {search_query}")
            search_response = perform_google_search(search_query, self.session_id, company_name)
            search_results = search_response.get('organic', []) if search_response else []
            
            if search_results:
                search_context = "\\n".join([f"Title: {r.get('title', '')}\\nSnippet: {r.get('snippet', '')}" for r in search_results])
                full_context += "\\n--- Dynamic Search Results ---\\n" + search_context

                if str(criterion.get('Deep Analysis')).lower() == 'true':
                    # Use async or sync scraping based on configuration
                    if ASYNC_SCRAPING_CONFIG['enable_async_scraping']:
                        log_info(f"🐝 Starting async deep analysis with signals for '{search_query}'...")
                        try:
                            scraped_text = run_async_scrape_sync(
                                search_results, criterion, self.session_id, company_name, search_query, 
                                max_concurrent=ASYNC_SCRAPING_CONFIG['max_concurrent_scrapes']
                            )
                            if scraped_text:
                                full_context += "\\n--- Deep Analysis Content (Async) ---\\n" + scraped_text
                        except Exception as e:
                            log_error(f"❌ Async scraping failed: {e}")
                            if ASYNC_SCRAPING_CONFIG['fallback_to_sync']:
                                log_info("🔄 Falling back to sync scraping...")
                                scraped_text = scrape_multiple_urls_with_signals(
                                    search_results, criterion, self.session_id, company_name, search_query
                                )
                                if scraped_text:
                                    full_context += "\\n--- Deep Analysis Content (Sync Fallback) ---\\n" + scraped_text
                    else:
                        log_info(f"🐝 Starting sync deep analysis with signals for '{search_query}'...")
                        scraped_text = scrape_multiple_urls_with_signals(
                            search_results, criterion, self.session_id, company_name, search_query
                        )
                        if scraped_text:
                            full_context += "\\n--- Deep Analysis Content ---\\n" + scraped_text
        
        # Enhance prompt with signals context
        signals_keywords = extract_signals_keywords(criterion)
        signals_context = ""
        if signals_keywords:
            signals_context = f"\\nKey signals to look for: {', '.join(signals_keywords)}"
        
        prompt = f"""
        Context:
        {full_context}
        ---
        Criterion: {criterion_text}{signals_context}
        ---
        Based on the context, does the company meet the criterion? 
        {f"Pay special attention to mentions of: {', '.join(signals_keywords)}" if signals_keywords else ""}
        Respond with "Yes" or "No" and a brief, one-sentence explanation.
        Example: Yes, the company provides cloud services which aligns with the criterion.
        """
        
        response_text = self._get_gpt_response(prompt)
        parsed_response = GPTResponse(response_text)
        return parsed_response.is_yes(), parsed_response.get_reason(), response_text

    def _perform_deep_analysis_for_criterion(self, company_name: str, search_results: list, serper_query: str) -> str:
        """Выполняет глубокий анализ (скрапинг) для одного критерия."""
        if not search_results:
            return ""

        all_scraped_text = []
        for result in search_results[:3]: # Ограничиваем скрапинг 3 ссылками
            link = result.get('link')
            if not link:
                continue
            
            scraped_text = scrape_website_text(link, self.session_id, company_name, serper_query)
            if scraped_text:
                all_scraped_text.append(scraped_text)
        
        return "\\n\\n".join(all_scraped_text)

    def _get_gpt_response(self, prompt: str) -> str:
        """Отправляет запрос в GPT и возвращает текстовый ответ."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=100
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            log_error(f"Ошибка вызова OpenAI API: {e}")
            return f"Error: {e}"

    def _format_results(self, results: dict) -> dict:
        """Форматирует финальный результат для вывода."""
        output = {}
        for product, audiences in results.items():
            qualified_audiences = [a for a in audiences if a['Qualified']]
            if qualified_audiences:
                output[f"Qualified_{product}"] = "Yes"
                output[f"Qualified_Audiences_{product}"] = ", ".join([a['Target Audience'] for a in qualified_audiences])
            else:
                output[f"Qualified_{product}"] = "No"
        return output


class GPTResponse:
    """Класс для парсинга и хранения ответа от GPT."""
    def __init__(self, response_text: str):
        self.text = response_text.lower()
        self.original_text = response_text

    def is_yes(self) -> bool:
        """Проверяет, является ли ответ положительным."""
        return self.text.startswith('yes')

    def get_reason(self) -> str:
        """Извлекает причину из ответа."""
        match = re.search(r'yes,?(.*)', self.text, re.IGNORECASE)
        if not match:
            match = re.search(r'no,?(.*)', self.text, re.IGNORECASE)
        
        if match and match.group(1):
            return match.group(1).strip()
        
        # Если не удалось распарсить, возвращаем исходный текст
        return self.original_text 