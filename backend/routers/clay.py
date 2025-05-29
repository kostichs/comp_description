from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
import time
from datetime import datetime
import aiohttp
from openai import AsyncOpenAI
import os

from src.config import load_env_vars, load_llm_config
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient
from src.pipeline.core import process_companies

router = APIRouter(prefix="/api/clay", tags=["Clay Integration"])
logger = logging.getLogger(__name__)

class ClayCompanyRequest(BaseModel):
    companyName: str = Field(..., description="Company name")
    domain: Optional[str] = Field(None, description="Company domain/website")
    industry: Optional[str] = Field(None, description="Company industry")
    additional_context: Optional[str] = Field(None, description="Additional context")

class ClayCompanyResponse(BaseModel):
    Description: str = Field(..., description="Generated company description")
    Official_Website: Optional[str] = Field(None, description="Company website")
    LinkedIn_URL: Optional[str] = Field(None, description="LinkedIn URL")
    Timestamp: str = Field(..., description="Processing timestamp")
    Processing_Status: str = Field(default="completed", description="Processing status")

@router.get("/health")
async def clay_health_check():
    """Health check endpoint for Clay integration"""
    return {"status": "healthy", "service": "clay-integration"}

@router.post("/process-company", response_model=ClayCompanyResponse)
async def process_company_for_clay(request: ClayCompanyRequest):
    """
    Process a single company for Clay webhook integration.
    Uses EXACTLY the same algorithm as the main application.
    """
    logger.info(f"Clay - Processing company: {request.companyName}")
    
    try:
        # Подготавливаем данные для основного алгоритма
        company_data = {
            "name": request.companyName
        }
        
        # Добавляем URL если есть
        if request.domain:
            company_data["url"] = request.domain
        
        # Подготавливаем request_data в том же формате как в process_companies_direct
        main_request_data = {
            "companies": [company_data],
            "context_text": request.additional_context,
            "run_llm_deep_search": True,  # ВКЛЮЧАЕМ полный алгоритм
            "write_to_hubspot": False     # ОТКЛЮЧАЕМ HubSpot для Clay
        }
        
        # Используем ТОЧНО тот же код что в process_companies_direct
        logger.info("Clay - Loading environment variables")
        env_vars = load_env_vars()
        scrapingbee_api_key = env_vars[0]
        openai_api_key = env_vars[1] 
        serper_api_key = env_vars[2]
        
        logger.info("Clay - Loading LLM config")
        llm_config = load_llm_config("llm_config.yaml")
        
        # Initialize clients (ТОЧНО как в основном коде)
        async with aiohttp.ClientSession() as aiohttp_session:
            sb_client = CustomScrapingBeeClient(api_key=scrapingbee_api_key)
            openai_client = AsyncOpenAI(api_key=openai_api_key)
            
            # Convert companies to format expected by process_companies (ТОЧНО как в основном коде)
            company_names_for_processing = []
            for company in main_request_data["companies"]:
                name = company["name"]
                url = company.get("url")
                if url:
                    company_names_for_processing.append((name, url))
                else:
                    company_names_for_processing.append(name)
            
            logger.info("Clay - Calling main process_companies function")
            
            # Process companies (ТОЧНО как в основном коде)
            results = await process_companies(
                company_names=company_names_for_processing,
                openai_client=openai_client,
                aiohttp_session=aiohttp_session,
                sb_client=sb_client,
                serper_api_key=serper_api_key,
                llm_config=llm_config,
                raw_markdown_output_path=None,  # No file output for Clay
                batch_size=5,
                context_text=main_request_data.get("context_text"),
                run_llm_deep_search_pipeline_cfg=True,    # ВКЛЮЧАЕМ полный алгоритм
                broadcast_update=None,  # No real-time updates for Clay
                output_csv_path=None,   # No CSV output for Clay
                output_json_path=None,  # No JSON output for Clay
                expected_csv_fieldnames=["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp"],
                hubspot_client=None,    # ОТКЛЮЧАЕМ HubSpot для Clay
                use_raw_llm_data_as_description=True,  # ИСПОЛЬЗУЕМ сырые данные LLM как в основном коде
                csv_append_mode=False,
                json_append_mode=False,
                already_saved_count=0,
                write_to_hubspot=False  # ОТКЛЮЧАЕМ HubSpot для Clay
            )
            
            logger.info(f"Clay - Processing completed, got {len(results)} results")
            
            # Возвращаем результат для первой (единственной) компании
            if results and len(results) > 0:
                result = results[0]
                return ClayCompanyResponse(
                    Description=result.get("Description", f"Error processing {request.companyName}"),
                    Official_Website=result.get("Official_Website"),
                    LinkedIn_URL=result.get("LinkedIn_URL"), 
                    Timestamp=result.get("Timestamp", time.strftime("%Y-%m-%d %H:%M:%S")),
                    Processing_Status="completed"
                )
            else:
                logger.error("Clay - No results returned from process_companies")
                return ClayCompanyResponse(
                    Description=f"No results generated for {request.companyName}",
                    Official_Website="",
                    LinkedIn_URL="",
                    Timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                    Processing_Status="error"
                )
                
    except Exception as e:
        logger.error(f"Clay - Error processing {request.companyName}: {e}", exc_info=True)
        return ClayCompanyResponse(
            Description=f"Error processing {request.companyName}: {str(e)}",
            Official_Website="",
            LinkedIn_URL="", 
            Timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            Processing_Status="error"
        ) 