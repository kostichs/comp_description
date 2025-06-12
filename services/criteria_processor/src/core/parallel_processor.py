"""
Параллельный процессор, сохраняющий структуру "продукт за продуктом"
но ускоряющий обработку компаний внутри каждого продукта
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# Добавляем корень criteria_processor в sys.path
CRITERIA_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(CRITERIA_ROOT))

from src.data.loaders import load_data
from src.criteria.general import check_general_criteria
from src.criteria.qualification import check_qualification_questions
from src.criteria.mandatory import check_mandatory_criteria
from src.criteria.nth import check_nth_criteria
from src.formatters.json_format import create_structured_output
from src.data.savers import save_results
from src.utils.logging import log_info, log_error
from src.utils.config import PROCESSING_CONFIG, ASYNC_GPT_CONFIG, CIRCUIT_BREAKER_CONFIG
from src.utils.state_manager import ProcessingStateManager

# Import async components
from src.llm.async_gpt_analyzer import run_async_gpt_analysis_sync
from src.analysis.async_company_analyzer import run_async_company_analysis_sync


def process_single_company_for_product(args):
    """
    Обрабатывает одну компанию для одного продукта.
    Эта функция может выполняться параллельно для нескольких компаний.
    """
    company_row, product, product_data, general_status, session_id, use_deep_analysis = args
    
    company_data = company_row.to_dict()
    company_name = company_data.get("Company_Name", "Unknown")
    description = company_data.get("Description", "")
    
    log_info(f"🔄 [{product}] Обрабатываем: {company_name}")
    
    try:
        # Create SEPARATE record for this company-product combination
        record = {
            **company_data,  # Исходные данные компании
            "Product": product,  # Указываем для какого продукта эта запись
            "All_Results": {},  # JSON с ВСЕМИ результатами
            "Qualified_Products": "NOT QUALIFIED"  # По умолчанию негативный результат
        }
        
        # Initialize results for this product
        general_passed = general_status.get(company_name, False)
        
        # Get detailed general criteria results if available
        general_detailed_info = general_status.get(f"{company_name}_detailed", {})
        general_detailed_results = general_detailed_info.get("General_Detailed_Results", [])
        general_passed_count = general_detailed_info.get("General_Passed_Count", 0)
        general_total_count = general_detailed_info.get("General_Total_Count", 0)
        
        product_results = {
            "product": product,
            "general_status": general_passed,
            "general_criteria": {
                "passed": general_passed,
                "passed_count": general_passed_count,
                "total_count": general_total_count,
                "detailed_criteria": general_detailed_results
            },
            "qualification_results": {},
            "qualified_audiences": [],
            "detailed_results": {}
        }
        
        # CRITICAL: If general criteria failed, stop processing immediately
        if not general_passed:
            log_info(f"❌ [{product}] {company_name} НЕ ПРОШЛА general критерии - ПРЕРЫВАЕМ анализ")
            record["Qualified_Products"] = "NOT QUALIFIED - Failed General Criteria"
            record["All_Results"] = product_results
            return [record]
        
        # Check Qualification Questions for this product
        qualification_questions = product_data["qualification_questions"]
        temp_qualification_info = {}
        if PROCESSING_CONFIG['use_general_desc_for_qualification']:
            check_qualification_questions(description, temp_qualification_info, qualification_questions)
        
        # Record qualification results for ALL audiences
        for audience in qualification_questions.keys():
            qualification_result = temp_qualification_info.get(f"Qualification_{audience}", "No")
            product_results["qualification_results"][audience] = qualification_result
            
            if qualification_result == "Yes":
                product_results["qualified_audiences"].append(audience)
                log_info(f"✅ [{product}] {company_name} квалифицирована для: {audience}")
        
        # If no qualified audiences, record this as NOT QUALIFIED (failed qualification)
        if not product_results["qualified_audiences"]:
            log_info(f"❌ [{product}] {company_name} не квалифицирована - НЕ ДОШЛА до анализа критериев")
            record["Qualified_Products"] = "NOT QUALIFIED - Failed Qualification Questions"
            record["All_Results"] = product_results
            return [record]
        
        # Process each qualified audience with criteria batching
        results_list = []
        
        for audience in product_results["qualified_audiences"]:
            log_info(f"🎯 [{product}] {company_name} → {audience}")
            
            # Initialize detailed results for this audience
            audience_results = {
                "audience": audience,
                "qualification_status": "Passed",
                "mandatory_status": "Not Started",
                "mandatory_criteria": [],
                "nth_results": {},
                "final_status": "Failed"
            }
            
            # Check Mandatory Criteria with batching
            temp_mandatory_info = {
                "Company_Name": company_data.get("Company_Name"),
                "Official_Website": company_data.get("Official_Website"),
                "Description": description
            }
            
            mandatory_passed = check_mandatory_criteria_batch(
                temp_mandatory_info, audience, product_data["mandatory_df"], 
                session_id=session_id, use_deep_analysis=use_deep_analysis
            )
            
            # Get detailed mandatory results - они сохраняются в temp_mandatory_info функцией check_mandatory_criteria_batch
            mandatory_detailed = temp_mandatory_info.get(f"Mandatory_Detailed_{audience}", [])
            audience_results["mandatory_criteria"] = mandatory_detailed
            
            if not mandatory_passed:
                log_info(f"❌ [{product}] {company_name} mandatory НЕ пройдены для {audience} - НЕ ДОШЛА до NTH")
                audience_results["mandatory_status"] = "Failed"
                audience_results["final_status"] = "Failed Mandatory"
                product_results["detailed_results"][audience] = audience_results
                
                # Create NOT QUALIFIED record for failed mandatory
                failed_mandatory_record = record.copy()
                failed_mandatory_record["Qualified_Products"] = f"NOT QUALIFIED - Failed Mandatory Criteria for {audience}"
                failed_mandatory_record["All_Results"] = product_results
                results_list.append(failed_mandatory_record)
                continue
            
            log_info(f"✅ [{product}] {company_name} mandatory пройдены для {audience}")
            audience_results["mandatory_status"] = "Passed"
            
            # Check NTH Criteria with batching
            temp_nth_info = {
                "Company_Name": company_data.get("Company_Name"),
                "Official_Website": company_data.get("Official_Website"),
                "Description": description
            }
            
            check_nth_criteria_batch(
                temp_nth_info, audience, product_data["nth_df"], 
                session_id=session_id, use_deep_analysis=use_deep_analysis
            )
            
            # Record NTH results - они сохраняются в temp_nth_info функцией check_nth_criteria_batch
            nth_score = temp_nth_info.get(f"NTH_Score_{audience}", 0)
            nth_total = temp_nth_info.get(f"NTH_Total_{audience}", 0)
            nth_passed = temp_nth_info.get(f"NTH_Passed_{audience}", 0)
            nth_nd = temp_nth_info.get(f"NTH_ND_{audience}", 0)
            nth_detailed = temp_nth_info.get(f"NTH_Detailed_{audience}", [])
            
            # Calculate pass_rate safely
            if nth_total > 0:
                pass_rate = round(nth_passed / nth_total, 3)
                # Ensure valid float range
                if not isinstance(pass_rate, (int, float)) or not (-1e308 <= pass_rate <= 1e308):
                    pass_rate = 0.0
            else:
                pass_rate = 0.0
            
            audience_results["nth_results"] = {
                "score": nth_score,
                "total_criteria": nth_total,
                "passed_criteria": nth_passed,
                "nd_criteria": nth_nd,
                "pass_rate": pass_rate,
                "detailed_criteria": nth_detailed
            }
            
            # ВСЕГДА добавляем detailed_results для каждой проверенной аудитории
            product_results["detailed_results"][audience] = audience_results
            
            # ИСПРАВЛЕНИЕ ЛОГИКИ: если компания дошла до NTH, сохраняем результаты ВСЕГДА
            # независимо от счета (даже если nth_score = 0)
            
            if nth_score > 0:
                # SUCCESS! This is a QUALIFIED result with positive score
                audience_results["final_status"] = "Qualified"
                status_text = "QUALIFIED"
                log_message = f"🎉 [{product}] {company_name} QUALIFIED для {audience} (Score: {nth_score:.3f})"
            else:
                # This is also QUALIFIED (passed qualification/mandatory) but with 0 NTH score
                audience_results["final_status"] = "Qualified" 
                status_text = "QUALIFIED"
                log_message = f"✅ [{product}] {company_name} QUALIFIED для {audience} (Score: {nth_score:.3f}) - прошла все этапы"
            
            # Create readable text format for ALL completed NTH analyses
            result_text_parts = [
                f"{status_text}: {audience}",
                f"NTH Score: {nth_score:.3f}",
                f"Total NTH Criteria: {nth_total}",
                f"Passed: {nth_passed}",
                f"ND (No Data): {nth_nd}"
            ]
            
            result_text = "\n".join(result_text_parts)
            
            # Create a copy of the record for this completed analysis
            result_record = record.copy()
            result_record["Qualified_Products"] = result_text
            result_record["All_Results"] = product_results
            results_list.append(result_record)
            
            log_info(log_message)
        
        # If no results at all (no audiences analyzed), return the base record
        if not results_list:
            record["All_Results"] = product_results
            record["Qualified_Products"] = "NO AUDIENCES ANALYZED"
            results_list.append(record)
        
        return results_list
        
    except Exception as e:
        log_error(f"❌ Ошибка обработки {company_name} для продукта {product}: {e}")
        error_record = {
            **company_data,
            "Product": product,
            "Qualified_Products": f"ERROR: {str(e)}",
            "All_Results": {"error": str(e)}
        }
        return [error_record]


def check_mandatory_criteria_batch(company_info, audience, mandatory_df, session_id=None, use_deep_analysis=False):
    """Асинхронная проверка mandatory критериев с пакетной обработкой"""
    # Check for Circuit Breaker exceptions
    if CIRCUIT_BREAKER_CONFIG['enable_circuit_breaker']:
        from src.utils.circuit_breaker import CircuitOpenException
        try:
            pass  # Circuit breaker check happens in openai_client
        except CircuitOpenException as e:
            log_error(f"🔴 Circuit Breaker блокирует mandatory критерии для {audience}: {e}")
            return False  # Fail mandatory when circuit is open
    
    # Получаем state_manager если доступен
    state_manager = None
    if session_id:
        try:
            from src.utils.state_manager import ProcessingStateManager
            state_manager = ProcessingStateManager(session_id)
        except Exception as e:
            log_error(f"⚠️ Не удалось получить StateManager: {e}")
    
    if ASYNC_GPT_CONFIG['enable_async_gpt'] and not mandatory_df.empty:
        log_info(f"🤖 Using async GPT for mandatory criteria: {audience}")
        try:
            # ФИЛЬТРАЦИЯ: берем только критерии для конкретной аудитории
            audience_mandatory_df = mandatory_df[mandatory_df['Target Audience'] == audience].copy()
            
            if audience_mandatory_df.empty:
                log_info(f"⚠️ No mandatory criteria found for audience: {audience}")
                # Store empty detailed results when no criteria
                company_info[f"Mandatory_Detailed_{audience}"] = []
                return True  # Если нет mandatory критериев, считаем что passed
            
            log_info(f"📊 Filtering mandatory criteria: {len(mandatory_df)} total → {len(audience_mandatory_df)} for {audience}")
            
            # Build context for async GPT analysis
            company_name = company_info.get("Company_Name", "Unknown")
            description = company_info.get("Description", "")
            website = company_info.get("Official_Website", "")
            
            context = f"Company: {company_name}\nDescription: {description}\nWebsite: {website}"
            
            # Use async GPT analysis for FILTERED mandatory criteria
            result = run_async_gpt_analysis_sync(
                context, audience_mandatory_df, session_id, website,
                max_concurrent=ASYNC_GPT_CONFIG['max_concurrent_gpt_requests']
            )
            
            # Check if ALL mandatory criteria passed (for mandatory, ALL must pass)
            total_mandatory = len(audience_mandatory_df)
            passed_mandatory = 0
            detailed_mandatory_results = []
            
            # Process each mandatory criterion in detail
            for idx, (_, criterion_row) in enumerate(audience_mandatory_df.iterrows()):
                criterion_info = {
                    "criteria_text": criterion_row.get("Criteria", "Unknown"),
                    "result": "Unknown"
                }
                
                # ИСПРАВЛЕНИЕ: Более точное сопоставление для mandatory критериев
                found_result = False
                for key, value in result.items():
                    if key.startswith("Qualified_") and value == "Yes":
                        # Проверяем совпадение по индексу критерия
                        try:
                            key_index = int(key.split("_")[-1]) - 1  # GPT считает с 1, мы с 0
                            if key_index == idx:
                                criterion_info["result"] = "Pass"
                                passed_mandatory += 1
                                found_result = True
                                # Отслеживаем результат
                                if state_manager:
                                    state_manager.record_criterion_result("mandatory", "Pass")
                                break
                        except (ValueError, IndexError):
                            # Если не можем извлечь номер, пропускаем
                            continue
                
                if not found_result:
                    criterion_info["result"] = "Fail"
                    # Отслеживаем результат
                    if state_manager:
                        state_manager.record_criterion_result("mandatory", "Fail")
                
                detailed_mandatory_results.append(criterion_info)
            
            # Store detailed mandatory results in company_info for later retrieval
            company_info[f"Mandatory_Detailed_{audience}"] = detailed_mandatory_results
            
            mandatory_passed = passed_mandatory == total_mandatory
            log_info(f"✅ Mandatory results for {audience}: {passed_mandatory}/{total_mandatory} passed → {'PASS' if mandatory_passed else 'FAIL'}")
            
            return mandatory_passed
            
        except Exception as e:
            # Handle Circuit Breaker exceptions specially
            if CIRCUIT_BREAKER_CONFIG['enable_circuit_breaker']:
                from src.utils.circuit_breaker import CircuitOpenException
                if isinstance(e, CircuitOpenException):
                    log_error(f"🔴 Circuit Breaker открыт во время mandatory анализа: {e}")
                    return False  # Don't fallback when circuit is open
            
            log_error(f"❌ Async mandatory analysis failed: {e}")
            if ASYNC_GPT_CONFIG['fallback_to_sync']:
                log_info("🔄 Falling back to sync mandatory analysis...")
                sync_result = check_mandatory_criteria(company_info, audience, mandatory_df, session_id, use_deep_analysis)
                
                # Create detailed results from sync function results
                audience_mandatory_df = mandatory_df[mandatory_df['Target Audience'] == audience].copy()
                detailed_mandatory_results = []
                
                for _, criterion_row in audience_mandatory_df.iterrows():
                    crit_text = criterion_row.get("Criteria", "Unknown")
                    # Try to get result from sync function
                    sync_key = f"Mandatory_{audience}_{crit_text}"
                    sync_value = company_info.get(sync_key, "Unknown")
                    
                    criterion_info = {
                        "criteria_text": crit_text,
                        "result": "Pass" if sync_value == "Passed" else "Fail" if sync_value == "Not Passed" else "ND" if sync_value == "ND" else "Unknown"
                    }
                    
                    # Убираем отслеживание individual критериев
                    
                    detailed_mandatory_results.append(criterion_info)
                
                # Store detailed results
                company_info[f"Mandatory_Detailed_{audience}"] = detailed_mandatory_results
                return sync_result
            return False
    else:
        # Use original sync function
        sync_result = check_mandatory_criteria(company_info, audience, mandatory_df, session_id, use_deep_analysis)
        
        # Create detailed results from sync function results
        audience_mandatory_df = mandatory_df[mandatory_df['Target Audience'] == audience].copy()
        detailed_mandatory_results = []
        
        for _, criterion_row in audience_mandatory_df.iterrows():
            crit_text = criterion_row.get("Criteria", "Unknown")
            # Try to get result from sync function
            sync_key = f"Mandatory_{audience}_{crit_text}"
            sync_value = company_info.get(sync_key, "Unknown")
            
            criterion_info = {
                "criteria_text": crit_text,
                "result": "Pass" if sync_value == "Passed" else "Fail" if sync_value == "Not Passed" else "ND" if sync_value == "ND" else "Unknown"
            }
            
            # Убираем отслеживание individual критериев
            
            detailed_mandatory_results.append(criterion_info)
        
        # Store detailed results
        company_info[f"Mandatory_Detailed_{audience}"] = detailed_mandatory_results
        return sync_result


def check_nth_criteria_batch(company_info, audience, nth_df, session_id=None, use_deep_analysis=False):
    """Асинхронная проверка NTH критериев с пакетной обработкой"""
    # Check for Circuit Breaker exceptions  
    if CIRCUIT_BREAKER_CONFIG['enable_circuit_breaker']:
        from src.utils.circuit_breaker import CircuitOpenException
        try:
            pass  # Circuit breaker check happens in openai_client
        except CircuitOpenException as e:
            log_error(f"🔴 Circuit Breaker блокирует NTH критерии для {audience}: {e}")
            # For NTH, set default values instead of failing
            company_info[f"NTH_Score_{audience}"] = 0
            company_info[f"NTH_Total_{audience}"] = 0
            company_info[f"NTH_Passed_{audience}"] = 0
            company_info[f"NTH_ND_{audience}"] = 0
            return
    
    # Получаем state_manager если доступен
    state_manager = None
    if session_id:
        try:
            from src.utils.state_manager import ProcessingStateManager
            state_manager = ProcessingStateManager(session_id)
        except Exception as e:
            log_error(f"⚠️ Не удалось получить StateManager: {e}")
    
    if ASYNC_GPT_CONFIG['enable_async_gpt'] and not nth_df.empty:
        log_info(f"🤖 Using async GPT for NTH criteria: {audience}")
        try:
            # ФИЛЬТРАЦИЯ: берем только критерии для конкретной аудитории
            audience_nth_df = nth_df[nth_df['Target Audience'] == audience].copy()
            
            if audience_nth_df.empty:
                log_info(f"⚠️ No NTH criteria found for audience: {audience}")
                company_info[f"NTH_Score_{audience}"] = 0
                company_info[f"NTH_Total_{audience}"] = 0
                company_info[f"NTH_Passed_{audience}"] = 0
                company_info[f"NTH_ND_{audience}"] = 0
                # Store empty detailed results when no criteria
                company_info[f"NTH_Detailed_{audience}"] = []
                return
            
            log_info(f"📊 Filtering NTH criteria: {len(nth_df)} total → {len(audience_nth_df)} for {audience}")
            
            # Build context for async GPT analysis
            company_name = company_info.get("Company_Name", "Unknown")
            description = company_info.get("Description", "")
            website = company_info.get("Official_Website", "")
            
            context = f"Company: {company_name}\nDescription: {description}\nWebsite: {website}"
            
            # Use async GPT analysis for FILTERED NTH criteria
            result = run_async_gpt_analysis_sync(
                context, audience_nth_df, session_id, website,
                max_concurrent=ASYNC_GPT_CONFIG['max_concurrent_gpt_requests']
            )
            
            # Extract detailed NTH results and update company_info
            qualified_count = 0
            total_criteria = len(audience_nth_df)
            detailed_criteria_results = []
            
            # Process each criterion in detail
            for idx, (_, criterion_row) in enumerate(audience_nth_df.iterrows()):
                criterion_info = {
                    "criteria_text": criterion_row.get("Criteria", "Unknown"),
                    "result": "Unknown"
                }
                
                # ИСПРАВЛЕНИЕ: Более точное сопоставление результатов GPT
                criterion_text = criterion_info["criteria_text"]
                found_match = False
                
                for key, value in result.items():
                    if key.startswith("Qualified_") and value == "Yes":
                        # Проверяем совпадение по индексу критерия
                        # Извлекаем номер из ключа (например "Qualified_1" -> 1)
                        try:
                            key_index = int(key.split("_")[-1]) - 1  # GPT считает с 1, мы с 0
                            if key_index == idx:
                                criterion_info["result"] = "Pass"
                                qualified_count += 1
                                found_match = True
                                                    # Убираем отслеживание individual критериев
                                break
                        except (ValueError, IndexError):
                            # Если не можем извлечь номер, используем старую логику
                            continue
                
                if not found_match:
                    criterion_info["result"] = "Fail"
                    # Убираем отслеживание individual критериев
                
                detailed_criteria_results.append(criterion_info)
            
            # Calculate NTH score (ensure valid float)
            if total_criteria > 0:
                nth_score = qualified_count / total_criteria
                # Ensure the score is a valid float
                if not isinstance(nth_score, (int, float)) or not (-1e308 <= nth_score <= 1e308):
                    nth_score = 0.0
            else:
                nth_score = 0.0
            
            # Update company_info with both summary and detailed results
            company_info[f"NTH_Score_{audience}"] = nth_score
            company_info[f"NTH_Total_{audience}"] = total_criteria
            company_info[f"NTH_Passed_{audience}"] = qualified_count
            company_info[f"NTH_ND_{audience}"] = total_criteria - qualified_count
            company_info[f"NTH_Detailed_{audience}"] = detailed_criteria_results
            
            log_info(f"✅ NTH results for {audience}: {qualified_count}/{total_criteria} passed (Score: {nth_score:.3f})")
            
        except Exception as e:
            # Handle Circuit Breaker exceptions specially
            if CIRCUIT_BREAKER_CONFIG['enable_circuit_breaker']:
                from src.utils.circuit_breaker import CircuitOpenException
                if isinstance(e, CircuitOpenException):
                    log_error(f"🔴 Circuit Breaker открыт во время NTH анализа: {e}")
                    # Set default values when circuit is open
                    company_info[f"NTH_Score_{audience}"] = 0
                    company_info[f"NTH_Total_{audience}"] = 0
                    company_info[f"NTH_Passed_{audience}"] = 0
                    company_info[f"NTH_ND_{audience}"] = 0
                    return
            
            log_error(f"❌ Async NTH analysis failed: {e}")
            if ASYNC_GPT_CONFIG['fallback_to_sync']:
                log_info("🔄 Falling back to sync NTH analysis...")
                check_nth_criteria(company_info, audience, nth_df, session_id, use_deep_analysis)
                
                # Create detailed results from sync function results
                audience_nth_df = nth_df[nth_df['Target Audience'] == audience].copy()
                detailed_criteria_results = []
                qualified_count = 0
                total_criteria = len(audience_nth_df)
                
                for _, criterion_row in audience_nth_df.iterrows():
                    crit_text = criterion_row.get("Criteria", "Unknown")
                    # Try to get result from sync function
                    sync_key = f"NTH_{audience}_{crit_text}"
                    sync_value = company_info.get(sync_key, "Unknown")
                    
                    criterion_info = {
                        "criteria_text": crit_text,
                        "result": "Pass" if sync_value == "Passed" else "Fail" if sync_value == "Not Passed" else "ND" if sync_value == "ND" else "Unknown"
                    }
                    
                    if sync_value == "Passed":
                        qualified_count += 1
                    
                    # Убираем отслеживание individual критериев
                    
                    detailed_criteria_results.append(criterion_info)
                
                # Store detailed results if not already set by sync function
                if f"NTH_Detailed_{audience}" not in company_info:
                    company_info[f"NTH_Detailed_{audience}"] = detailed_criteria_results
    else:
        # Use original sync function
        check_nth_criteria(company_info, audience, nth_df, session_id, use_deep_analysis)
        
        # Create detailed results from sync function results
        audience_nth_df = nth_df[nth_df['Target Audience'] == audience].copy()
        detailed_criteria_results = []
        qualified_count = 0
        total_criteria = len(audience_nth_df)
        
        for _, criterion_row in audience_nth_df.iterrows():
            crit_text = criterion_row.get("Criteria", "Unknown")
            # Try to get result from sync function
            sync_key = f"NTH_{audience}_{crit_text}"
            sync_value = company_info.get(sync_key, "Unknown")
            
            criterion_info = {
                "criteria_text": crit_text,
                "result": "Pass" if sync_value == "Passed" else "Fail" if sync_value == "Not Passed" else "ND" if sync_value == "ND" else "Unknown"
            }
            
            if sync_value == "Passed":
                qualified_count += 1
            
            # Убираем отслеживание individual критериев
            
            detailed_criteria_results.append(criterion_info)
        
        # Store detailed results if not already set by sync function
        if f"NTH_Detailed_{audience}" not in company_info:
            company_info[f"NTH_Detailed_{audience}"] = detailed_criteria_results


def run_parallel_analysis(companies_file=None, load_all_companies=False, session_id=None, use_deep_analysis=False, max_concurrent_companies=12, selected_products=None):
    """
    Параллельный анализ: ПРАВИЛЬНЫЙ ПОРЯДОК - каждая компания через все продукты параллельно
    """
    try:
        # Load all data
        log_info("🔄 Загружаем данные...")
        data_dict = load_data(
            companies_file=companies_file,
            load_all_companies=load_all_companies,
            selected_products=selected_products
        )
        
        companies_df = data_dict["companies"]
        products = data_dict["products"]
        products_data = data_dict["products_data"]
        general_criteria = data_dict["general_criteria"]
        
        log_info(f"🏢 ИСПРАВЛЕННЫЙ ПАРАЛЛЕЛЬНЫЙ ПОРЯДОК: Каждая компания через все продукты")
        log_info(f"📊 Компаний: {len(companies_df)}")
        log_info(f"📦 Продукты: {', '.join(products)}")
        log_info(f"🎯 Ожидаем записей: {len(companies_df)} × {len(products)} = {len(companies_df) * len(products)}")
        
        # Initialize state manager for this session  
        state_manager = None
        if session_id:
            try:
                from src.utils.state_manager import ProcessingStateManager
                state_manager = ProcessingStateManager(session_id)
                state_manager.update_totals(len(products), len(companies_df))
                # Инициализируем счетчики критериев с реалистичными оценками
                state_manager.initialize_criteria_totals(products_data, len(companies_df), general_criteria)
            except Exception as e:
                log_error(f"⚠️ Не удалось инициализировать StateManager: {e}")
        
        # 1. Check General Criteria ONCE for all companies
        log_info(f"\n🌐 Этап 1: Проверяем General критерии для ВСЕХ компаний...")
        general_status = {}
        
        for index, company_row in companies_df.iterrows():
            company_data = company_row.to_dict()
            company_name = company_data.get("Company_Name", "Unknown")
            description = company_data.get("Description", "")
            
            log_info(f"🌐 General для: {company_name}")
            
            try:
                temp_general_info = {}
                general_passed = check_general_criteria(description, temp_general_info, general_criteria)
                general_status[company_name] = general_passed
                
                # Store detailed general criteria information
                general_status[f"{company_name}_detailed"] = temp_general_info
                
                # Не отслеживаем individual критерии, только компании
                
                if general_passed:
                    log_info("✅ General пройдены")
                else:
                    log_info("❌ General НЕ пройдены")
                
                # Save progress for general criteria
                if state_manager:
                    state_manager.save_progress(0, index + 1, stage="general_criteria")
                    
            except Exception as e:
                log_error(f"❌ Ошибка проверки general критериев для {company_name}: {e}")
                general_status[company_name] = False
                # Убираем отслеживание individual критериев
                if state_manager:
                    state_manager.save_progress(0, index + 1, stage="general_criteria")
        
        # 2. ПРАВИЛЬНЫЙ ПОРЯДОК: Process each COMPANY through all PRODUCTS
        all_results = []

        def process_single_company_all_products(company_args):
            """
            Обрабатывает ОДНУ компанию через ВСЕ продукты.
            Возвращает ОДНУ объединенную запись с результатами по всем продуктам.
            """
            company_row, products_data, general_status, session_id, use_deep_analysis = company_args
            
            company_data = company_row.to_dict()
            company_name = company_data.get("Company_Name", "Unknown")
            
            log_info(f"🏢 Обрабатываем компанию: {company_name} через ВСЕ продукты: {', '.join(products)}")
            
            # Create ONE consolidated record for this company
            consolidated_record = {
                **company_data,  # Базовые данные компании
                "All_Results": {},  # JSON со ВСЕМИ продуктами и результатами
                "Qualified_Products": ""  # Текстовые результаты по всем продуктам
            }
            
            all_products_results = {}
            qualified_products_text = []
            
            # Process this company through ALL products
            for product in products:
                try:
                    log_info(f"  📦 {company_name} → {product}")
                    
                    # Use the existing function for this company-product combination
                    args = (company_row, product, products_data[product], general_status, session_id, use_deep_analysis)
                    product_results = process_single_company_for_product(args)
                    
                    # Extract the product results from the returned list
                    if product_results and len(product_results) > 0:
                        # Get the All_Results from the first result (they should all be the same for this product)
                        product_result = product_results[0]
                        product_all_results = product_result.get("All_Results", {})
                        product_qualified_text = product_result.get("Qualified_Products", "")
                        
                        # Store results for this product
                        all_products_results[product] = product_all_results
                        
                        # Add to qualified products text
                        if product_qualified_text and product_qualified_text != "NOT QUALIFIED":
                            qualified_products_text.append(f"=== {product.upper()} ===\n{product_qualified_text}")
                        else:
                            qualified_products_text.append(f"=== {product.upper()} ===\nNOT QUALIFIED")
                    
                except Exception as e:
                    log_error(f"  ❌ Ошибка обработки {company_name} для продукта {product}: {e}")
                    all_products_results[product] = {"error": str(e)}
                    qualified_products_text.append(f"=== {product.upper()} ===\nERROR: {str(e)}")
            
            # Consolidate all results
            consolidated_record["All_Results"] = all_products_results
            consolidated_record["Qualified_Products"] = "\n\n".join(qualified_products_text) if qualified_products_text else "NOT QUALIFIED"
            
            log_info(f"✅ Завершена обработка компании {company_name}: ОДНА консолидированная запись с {len(products)} продуктами")
            return [consolidated_record]  # Return as list for consistency
        
        # ПАРАЛЛЕЛЬНАЯ ОБРАБОТКА компаний (каждая компания через ВСЕ продукты)
        log_info(f"\n🚀 Этап 2: ПРАВИЛЬНЫЙ ПОРЯДОК - каждая компания через все продукты")
        log_info(f"⚡ Компании: {len(companies_df)}")
        log_info(f"📦 Продукты: {', '.join(products)}")
        log_info(f"📊 Ожидаем записей: {len(companies_df)} (по одной на компанию с консолидированными результатами)")
        
        # Подготавливаем аргументы для параллельной обработки
        company_args = []
        for index, company_row in companies_df.iterrows():
            args = (company_row, products_data, general_status, session_id, use_deep_analysis)
            company_args.append(args)
        
        # ПАРАЛЛЕЛЬНАЯ ОБРАБОТКА компаний с Circuit Breaker
        circuit_breaker_triggered = False
        
        try:
            with ThreadPoolExecutor(max_workers=max_concurrent_companies) as executor:
                # Отправляем все компании для обработки через ВСЕ продукты
                future_to_company = {
                    executor.submit(process_single_company_all_products, args): args[0].get("Company_Name", f"Company_{i}")
                    for i, args in enumerate(company_args)
                }
                
                # Собираем результаты по мере завершения
                for future in as_completed(future_to_company):
                    company_name = future_to_company[future]
                    try:
                        company_results = future.result()
                        all_results.extend(company_results)
                        log_info(f"🎉 Компания {company_name} завершена: {len(company_results)} записей")
                        
                        # Mark company as completed in state manager (для всех продуктов)
                        if state_manager:
                            for product in products:
                                state_manager.mark_company_completed(company_name, product, success=True)
                                
                    except Exception as e:
                        # Handle Circuit Breaker exceptions
                        if CIRCUIT_BREAKER_CONFIG['enable_circuit_breaker']:
                            from src.utils.circuit_breaker import CircuitOpenException
                            if isinstance(e, CircuitOpenException):
                                log_error(f"🔴 Circuit Breaker сработал для {company_name}: {e}")
                                circuit_breaker_triggered = True
                                if state_manager:
                                    state_manager.record_circuit_breaker_event("triggered_during_processing", {
                                        "company": company_name,
                                        "error": str(e)
                                    })
                                break  # Stop processing
                        
                        log_error(f"❌ Ошибка обработки компании {company_name}: {e}")
                        if state_manager:
                            for product in products:
                                state_manager.mark_company_completed(company_name, product, success=False)
            
            # Save partial results
            if state_manager and all_results:
                state_manager.save_partial_results(all_results)
                
        except Exception as e:
            log_error(f"❌ Критическая ошибка параллельной обработки: {e}")
            if state_manager:
                state_manager.record_circuit_breaker_event("critical_error", {
                    "error": str(e),
                    "stage": "parallel_processing"
                })
        
        # Count qualified companies
        qualified_count = sum(1 for result in all_results if result["Qualified_Products"] != "NOT QUALIFIED")
        
        # Save results
        log_info("💾 Сохраняем результаты...")
        json_path, csv_path = save_results(all_results, "PARALLEL_BY_COMPANIES", session_id=session_id)
        
        log_info(f"""
🎉 Параллельная обработка завершена (КОНСОЛИДИРОВАННЫЕ РЕЗУЛЬТАТЫ):
   🏢 Компании: {len(companies_df)}
   📦 Продукты: {', '.join(products)}
   📊 Записей (одна на компанию): {len(all_results)}
   ✅ Компаний с квалификацией: {qualified_count}
   📄 JSON результаты: {json_path}
   📋 CSV результаты: {csv_path}""")
        
        # Mark session as completed
        if state_manager:
            state_manager.mark_completed("completed")
        
        return all_results
        
    except Exception as e:
        log_error(f"❌ Критическая ошибка параллельного анализа: {e}")
        raise 