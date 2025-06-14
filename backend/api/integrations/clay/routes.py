from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
import time
from datetime import datetime
import aiohttp
from openai import AsyncOpenAI
import os
import uuid
import asyncio

from src.config import load_env_vars, load_llm_config
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient
from src.pipeline.core import process_companies

router = APIRouter(prefix="/integrations/clay", tags=["Clay Integration"])
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

# Новая модель для асинхронного запроса
class ClayAsyncRequest(BaseModel):
    companyName: str = Field(..., description="Company name")
    domain: Optional[str] = Field(None, description="Company domain/website")
    industry: Optional[str] = Field(None, description="Company industry")
    additional_context: Optional[str] = Field(None, description="Additional context")
    clay_webhook_url: str = Field(..., description="Clay webhook URL для отправки результатов")

class ClayAsyncResponse(BaseModel):
    status: str = Field(default="accepted", description="Request status")
    task_id: str = Field(..., description="Unique task identifier")
    message: str = Field(..., description="Status message")

# Словарь для хранения запущенных задач (в продакшене лучше использовать Redis)
active_tasks = {}

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

@router.post("/process-company-async", response_model=ClayAsyncResponse)
async def process_company_async_for_clay(request: ClayAsyncRequest, background_tasks: BackgroundTasks):
    """
    Асинхронная обработка компании для Clay.
    Возвращает сразу 200 OK, а результаты отправляет на Clay webhook позже.
    """
    # Генерируем уникальный ID задачи
    task_id = str(uuid.uuid4())
    
    logger.info(f"Clay Async - Received request for {request.companyName}, task_id: {task_id}")
    
    # Сохраняем задачу как активную
    active_tasks[task_id] = {
        "status": "processing",
        "company_name": request.companyName,
        "started_at": datetime.now(),
        "webhook_url": request.clay_webhook_url
    }
    
    # Запускаем фоновую обработку
    background_tasks.add_task(
        process_and_send_to_clay_webhook,
        task_id,
        request
    )
    
    return ClayAsyncResponse(
        status="accepted",
        task_id=task_id,
        message=f"Processing started for {request.companyName}. Results will be sent to Clay webhook when ready."
    )

async def process_and_send_to_clay_webhook(task_id: str, request: ClayAsyncRequest):
    """
    Фоновая функция для обработки компании и отправки результатов на Clay webhook
    """
    try:
        logger.info(f"Clay Async Background - Starting processing for task {task_id}")
        
        # Обновляем статус
        if task_id in active_tasks:
            active_tasks[task_id]["status"] = "processing"
        
        # Подготавливаем данные для основного алгоритма
        company_data = {"name": request.companyName}
        if request.domain:
            company_data["url"] = request.domain
        
        main_request_data = {
            "companies": [company_data],
            "context_text": request.additional_context,
            "run_llm_deep_search": True,
            "write_to_hubspot": False
        }
        
        # Загружаем конфигурацию
        env_vars = load_env_vars()
        scrapingbee_api_key = env_vars[0]
        openai_api_key = env_vars[1]
        serper_api_key = env_vars[2]
        llm_config = load_llm_config("llm_config.yaml")
        
        # Обрабатываем компанию
        async with aiohttp.ClientSession() as aiohttp_session:
            sb_client = CustomScrapingBeeClient(api_key=scrapingbee_api_key)
            openai_client = AsyncOpenAI(api_key=openai_api_key)
            
            company_names_for_processing = []
            for company in main_request_data["companies"]:
                name = company["name"]
                url = company.get("url")
                if url:
                    company_names_for_processing.append((name, url))
                else:
                    company_names_for_processing.append(name)
            
            logger.info(f"Clay Async Background - Processing company {request.companyName}")
            
            results = await process_companies(
                company_names=company_names_for_processing,
                openai_client=openai_client,
                aiohttp_session=aiohttp_session,
                sb_client=sb_client,
                serper_api_key=serper_api_key,
                llm_config=llm_config,
                raw_markdown_output_path=None,
                batch_size=5,
                context_text=main_request_data.get("context_text"),
                run_llm_deep_search_pipeline_cfg=True,
                broadcast_update=None,
                output_csv_path=None,
                output_json_path=None,
                expected_csv_fieldnames=["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp"],
                hubspot_client=None,
                use_raw_llm_data_as_description=True,
                csv_append_mode=False,
                json_append_mode=False,
                already_saved_count=0,
                write_to_hubspot=False
            )
            
            logger.info(f"Clay Async Background - Processing completed for task {task_id}")
            
            # Подготавливаем данные для отправки в Clay
            if results and len(results) > 0:
                result = results[0]
                clay_webhook_data = {
                    "task_id": task_id,
                    "companyName": request.companyName,
                    "domain": request.domain,
                    "Description": result.get("Description", f"Error processing {request.companyName}"),
                    "Official_Website": result.get("Official_Website"),
                    "LinkedIn_URL": result.get("LinkedIn_URL"),
                    "Timestamp": result.get("Timestamp", time.strftime("%Y-%m-%d %H:%M:%S")),
                    "Processing_Status": "completed"
                }
            else:
                clay_webhook_data = {
                    "task_id": task_id,
                    "companyName": request.companyName,
                    "domain": request.domain,
                    "Description": f"No results generated for {request.companyName}",
                    "Official_Website": "",
                    "LinkedIn_URL": "",
                    "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "Processing_Status": "error"
                }
            
            # Отправляем результаты на Clay webhook
            await send_to_clay_webhook(request.clay_webhook_url, clay_webhook_data, task_id)
            
            # Обновляем статус задачи
            if task_id in active_tasks:
                active_tasks[task_id].update({
                    "status": "completed",
                    "completed_at": datetime.now(),
                    "result": clay_webhook_data
                })
                
    except Exception as e:
        logger.error(f"Clay Async Background - Error processing task {task_id}: {e}", exc_info=True)
        
        # Отправляем ошибку на Clay webhook
        error_data = {
            "task_id": task_id,
            "companyName": request.companyName,
            "domain": request.domain,
            "Description": f"Error processing {request.companyName}: {str(e)}",
            "Official_Website": "",
            "LinkedIn_URL": "",
            "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "Processing_Status": "error"
        }
        
        await send_to_clay_webhook(request.clay_webhook_url, error_data, task_id)
        
        # Обновляем статус задачи
        if task_id in active_tasks:
            active_tasks[task_id].update({
                "status": "error",
                "completed_at": datetime.now(),
                "error": str(e)
            })

async def send_to_clay_webhook(webhook_url: str, data: Dict[str, Any], task_id: str):
    """
    Отправляет данные на Clay webhook
    """
    try:
        logger.info(f"Clay Webhook - Sending data to {webhook_url} for task {task_id}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    logger.info(f"Clay Webhook - Successfully sent data for task {task_id}")
                else:
                    logger.error(f"Clay Webhook - Failed to send data for task {task_id}, status: {response.status}")
                    response_text = await response.text()
                    logger.error(f"Clay Webhook - Response: {response_text}")
                    
    except Exception as e:
        logger.error(f"Clay Webhook - Error sending data for task {task_id}: {e}")

@router.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    """
    Получить статус обработки задачи (опциональный endpoint для отладки)
    """
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return active_tasks[task_id]

@router.get("/active-tasks")
async def get_active_tasks():
    """
    Получить список всех активных задач (для мониторинга)
    """
    return {
        "total_tasks": len(active_tasks),
        "tasks": active_tasks
    } 