import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from src.pipeline.core import _process_single_company_async
from finders.llm_deep_search_finder import LLMDeepSearchFinder

@pytest.mark.asyncio
async def test_url_extraction_from_llm_deep_search():
    """Тест проверяет, что URL, извлеченный из результата LLMDeepSearchFinder, сохраняется в результате."""
    
    # Создаем мок для finder_instances
    finder_instances = {
        "llm_deep_search_finder": AsyncMock()
    }
    
    # Настраиваем мок для finder.find
    mock_extracted_url = "https://example.com"
    finder_instances["llm_deep_search_finder"].find.return_value = {
        "source": "llm_deep_search",
        "result": "Some result text",
        "raw_result": "Some result text",
        "sources": [],
        "extracted_homepage_url": mock_extracted_url,
        "_finder_instance_type": "LLMDeepSearchFinder"
    }
    
    # Создаем остальные моки
    mock_openai_client = MagicMock()
    mock_aiohttp_session = MagicMock()
    mock_sb_client = MagicMock()
    mock_description_generator = AsyncMock()
    mock_description_generator.generate.return_value = "Generated description"
    
    # Вызываем функцию _process_single_company_async
    result = await _process_single_company_async(
        company_name="Test Company",
        openai_client=mock_openai_client,
        aiohttp_session=mock_aiohttp_session,
        sb_client=mock_sb_client,
        serper_api_key="dummy_key",
        finder_instances=finder_instances,
        description_generator=mock_description_generator,
        llm_config={},
        raw_markdown_output_path=None,
        output_csv_path=None,
        output_json_path=None,
        csv_fields=["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp"],
        company_index=0,
        total_companies=1,
        run_llm_deep_search_pipeline=True,
        run_standard_homepage_finders=False
    )
    
    # Проверяем, что URL был сохранен в результате
    assert result["Official_Website"] == mock_extracted_url 