"""
Pipeline Markdown Utilities

This module provides functions for generating and saving markdown reports.
"""

import logging
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

async def translate_to_english_if_needed(text: str, openai_client: AsyncOpenAI) -> str:
    """
    Принудительно переводит весь текст на английский язык.
    
    Args:
        text: Исходный текст
        openai_client: Клиент OpenAI
        
    Returns:
        str: Переведенный текст
    """
    try:
        logger.info(f"Выполняется принудительный перевод на английский (длина текста: {len(text)})")
        
        # Разбиваем текст на части, если он слишком большой
        chunk_size = 8000  # Максимальный размер чанка для перевода
        chunks = []
        
        if len(text) > chunk_size:
            # Разбиваем по маркерам заголовков, чтобы не разрывать структуру
            parts = re.split(r'(\n##? )', text)
            current_chunk = ""
            
            for i, part in enumerate(parts):
                if i % 2 == 1:  # Это маркер заголовка
                    current_chunk += part
                    continue
                
                if len(current_chunk) + len(part) < chunk_size:
                    current_chunk += part
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = part
            
            if current_chunk:
                chunks.append(current_chunk)
        else:
            chunks = [text]
        
        translated_chunks = []
        logger.info(f"Текст разбит на {len(chunks)} частей для перевода")
        
        # Переводим каждую часть отдельно
        for i, chunk in enumerate(chunks):
            logger.info(f"Переводится часть {i+1} из {len(chunks)} (размер: {len(chunk)})")
            response = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional translator. Your task is to translate ALL content to English, including ALL Arabic, Chinese, Russian or any other non-English text. Preserve markdown formatting exactly as it appears in the original text. Keep proper names similar to the original but add English translation in parentheses when needed. This is MANDATORY."},
                    {"role": "user", "content": f"Translate the following text to English, ensuring ALL non-English content is translated. Pay special attention to sections with Arabic, Chinese, or other non-Latin scripts. Preserve all markdown formatting:\n\n{chunk}"}
                ],
                temperature=0.1,
                max_tokens=10000
            )
            
            translated_chunk = response.choices[0].message.content
            translated_chunks.append(translated_chunk)
            logger.info(f"Часть {i+1} успешно переведена")
        
        translated_text = "\n".join(translated_chunks)
        logger.info(f"Весь текст успешно переведен на английский (новая длина: {len(translated_text)})")
        return translated_text
    except Exception as e:
        logger.error(f"Ошибка при переводе текста: {e}")
        return text  # В случае ошибки возвращаем исходный текст

async def generate_and_save_raw_markdown_report_async(
    company_name: str,
    company_findings: List[Dict[str, Any]],
    openai_client: AsyncOpenAI,
    llm_config: Dict[str, Any],
    markdown_output_path: Path
):
    """
    Форматирует сырые найденные данные в Markdown с помощью LLM и сохраняет в файл.
    
    Args:
        company_name: Название компании
        company_findings: Список найденных данных
        openai_client: Клиент OpenAI
        llm_config: Конфигурация LLM
        markdown_output_path: Путь для сохранения отчета
    """
    try:
        raw_data_parts = [f"# Raw Data Report for {company_name}\n"]
        for i, finding in enumerate(company_findings):
            source_name = finding.get("source", f"Unknown_Source_{i+1}")
            finder_type = finding.get("_finder_instance_type", source_name) 
            report_text_data = finding.get("result")
            error_data = finding.get("error")
            sources_list = finding.get("sources") 
            raw_data_parts.append(f"\n## Source: {source_name} (Type: {finder_type})\n")
            if error_data: raw_data_parts.append(f"**Error:**\n```\n{error_data}\n```\n")
            if report_text_data:
                raw_data_parts.append(f"**Report/Result Data:**\n")
                if isinstance(report_text_data, dict):
                    raw_data_parts.append(f"```json\n{json.dumps(report_text_data, indent=2, ensure_ascii=False)}\n```\n")
                else: raw_data_parts.append(f"```text\n{str(report_text_data)}\n```\n")
            if sources_list and isinstance(sources_list, list):
                raw_data_parts.append(f"**Extracted Sources from this source:**\n")
                for src_item in sources_list:
                    title = src_item.get('title', 'N/A'); url = src_item.get('url', 'N/A')
                    raw_data_parts.append(f"- [{title}]({url})\n")
            if not error_data and not report_text_data and not (sources_list and isinstance(sources_list, list)):
                 raw_data_parts.append("_No specific data, error, or sources reported by this finder._\n")
        raw_data_for_llm_prompt = "".join(raw_data_parts)
        
        if not raw_data_for_llm_prompt.strip() or len(raw_data_for_llm_prompt) < 50:
            logger.warning(f"No substantial raw data to format for {company_name}. Saving raw dump.")
            md_path = markdown_output_path / f"{company_name.replace(' ', '_').replace('/', '_')}_raw_data_dump.md"
            markdown_output_path.mkdir(parents=True, exist_ok=True); 
            with open(md_path, "w", encoding="utf-8") as f: f.write(raw_data_for_llm_prompt)
            logger.info(f"Saved raw dump for {company_name} to {md_path}"); return
        
        # ЭТАП 1: Обязательный перевод ВСЕГО текста на английский перед форматированием
        logger.info(f"Начинается перевод контента для {company_name}")
        translated_raw_data = await translate_to_english_if_needed(raw_data_for_llm_prompt, openai_client)
        logger.info(f"Перевод завершен, форматирование markdown")
        
        model_config = llm_config.get("raw_markdown_formatter_config", {})
        model = model_config.get("model", "gpt-4o-mini")
        temp = model_config.get("temperature", 0.1)
        max_tokens = model_config.get("max_tokens", 10000)
        system_prompt = (
            "You are an AI assistant. Your task is to take a collection of raw data entries for a company, each from a different named source, "
            "and format this information into a single, coherent, well-structured Markdown report. "
            "IMPORTANT FORMATTING RULES:\n"
            "1. Use exactly this format - numbered sections like '1. **Section Title:**' followed by list items\n"
            "2. List items must use asterisk format ('* **Item name:** value')\n"
            "3. No empty lines between list items within the same section\n"
            "4. Exactly ONE empty line between major numbered sections\n"
            "5. All content must always be in English - this is MANDATORY\n"
            "\n"
            "Preserve all information, including report texts, lists of URLs/sources, and any reported errors. "
            "Use Markdown headings for each original source. If a source provided a list of URLs (sources), list them clearly under that source's section."
        )
        user_prompt = (
            f"Please format the following raw data collection for the company '{company_name}' into a single, structured Markdown report. "
            "Make sure all details, including any explicitly listed URLs/sources from each original data block, are preserved and clearly presented under their respective original source headings.\n\n"
            "CRITICAL REQUIREMENTS:\n"
            "1. Format ALL lists using asterisks (*) with no empty lines between items in the same section.\n"
            "2. Use only ONE empty line between major numbered sections.\n"
            "3. For section formatting, use exactly: '1. **Section Title:**'\n"
            "4. For list items, use exactly: '* **Item name:** value'\n\n"
            f"Raw Data Collection:\n```markdown\n{translated_raw_data}\n```"
        )
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        logger.info(f"Generating formatted Markdown for {company_name} using {model}. Input length: {len(translated_raw_data)}")
        try:
            response = await openai_client.chat.completions.create(model=model, messages=messages, temperature=temp, max_tokens=max_tokens)
            if response.choices and response.choices[0].message and response.choices[0].message.content:
                md_content = response.choices[0].message.content.strip()
                md_path = markdown_output_path / f"{company_name.replace(' ', '_').replace('/', '_')}_raw_data_formatted_en.md"
                markdown_output_path.mkdir(parents=True, exist_ok=True); 
                with open(md_path, "w", encoding="utf-8") as f: f.write(md_content)
                logger.info(f"Saved formatted Markdown with English translation for {company_name} to {md_path}")
            else:
                logger.warning(f"LLM did not generate content for Markdown report for {company_name}. Saving unformatted dump.")
                md_path_dump = markdown_output_path / f"{company_name.replace(' ', '_').replace('/', '_')}_raw_data_unformatted_llm_empty.md"
                with open(md_path_dump, "w", encoding="utf-8") as f: f.write(translated_raw_data)
                logger.info(f"Saved unformatted dump to {md_path_dump}")
        except Exception as e_llm:
            logger.error(f"Error during LLM formatting for {company_name}: {e_llm}. Saving unformatted dump.", exc_info=True)
            md_path_error = markdown_output_path / f"{company_name.replace(' ', '_').replace('/', '_')}_raw_data_unformatted_llm_error.md"
            with open(md_path_error, "w", encoding="utf-8") as f: f.write(translated_raw_data)
            logger.info(f"Saved unformatted dump due to LLM error to {md_path_error}")
    except Exception as e:
        logger.error(f"General error in generate_and_save_raw_markdown_report_async for {company_name}: {e}", exc_info=True) 