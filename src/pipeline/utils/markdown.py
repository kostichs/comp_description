"""
Pipeline Markdown Utilities

This module provides functions for generating and saving markdown reports.
"""

import logging
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

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
        model_config = llm_config.get("raw_markdown_formatter_config", {})
        model = model_config.get("model", "gpt-4o-mini")
        temp = model_config.get("temperature", 0.1)
        max_tokens = model_config.get("max_tokens", 4000)
        system_prompt = (
            "You are an AI assistant. Your task is to take a collection of raw data entries for a company, each from a different named source, "
            "and format this information into a single, coherent, well-structured Markdown report. "
            "Preserve all information, including report texts, lists of URLs/sources, and any reported errors. "
            "Use Markdown headings for each original source. If a source provided a list of URLs (sources), list them clearly under that source's section. "
            "Do not summarize, omit, or interpret the data, simply reformat it for readability."
        )
        user_prompt = (
            f"Please format the following raw data collection for the company '{company_name}' into a single, structured Markdown report. "
            "Make sure all details, including any explicitly listed URLs/sources from each original data block, are preserved and clearly presented under their respective original source headings.\n\n"
            f"Raw Data Collection:\n```markdown\n{raw_data_for_llm_prompt}\n```"
        )
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        logger.info(f"Generating formatted Markdown for {company_name} using {model}. Input length: {len(raw_data_for_llm_prompt)}")
        try:
            response = await openai_client.chat.completions.create(model=model, messages=messages, temperature=temp, max_tokens=max_tokens)
            if response.choices and response.choices[0].message and response.choices[0].message.content:
                md_content = response.choices[0].message.content.strip()
                md_path = markdown_output_path / f"{company_name.replace(' ', '_').replace('/', '_')}_raw_data_formatted.md"
                markdown_output_path.mkdir(parents=True, exist_ok=True); 
                with open(md_path, "w", encoding="utf-8") as f: f.write(md_content)
                logger.info(f"Saved formatted Markdown for {company_name} to {md_path}")
            else:
                logger.warning(f"LLM did not generate content for Markdown report for {company_name}. Saving unformatted dump.")
                md_path_dump = markdown_output_path / f"{company_name.replace(' ', '_').replace('/', '_')}_raw_data_unformatted_llm_empty.md"
                with open(md_path_dump, "w", encoding="utf-8") as f: f.write(raw_data_for_llm_prompt)
                logger.info(f"Saved unformatted dump to {md_path_dump}")
        except Exception as e_llm:
            logger.error(f"Error during LLM formatting for {company_name}: {e_llm}. Saving unformatted dump.", exc_info=True)
            md_path_error = markdown_output_path / f"{company_name.replace(' ', '_').replace('/', '_')}_raw_data_unformatted_llm_error.md"
            with open(md_path_error, "w", encoding="utf-8") as f: f.write(raw_data_for_llm_prompt)
            logger.info(f"Saved unformatted dump due to LLM error to {md_path_error}")
    except Exception as e:
        logger.error(f"General error in generate_and_save_raw_markdown_report_async for {company_name}: {e}", exc_info=True) 