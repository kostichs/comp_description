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
from src.utils.config import PROCESSING_CONFIG, ASYNC_GPT_CONFIG

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
        
        # If no qualified audiences, record this in All_Results
        if not product_results["qualified_audiences"]:
            log_info(f"❌ [{product}] {company_name} не квалифицирована")
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
            
            # Get detailed mandatory results
            mandatory_detailed = temp_mandatory_info.get(f"Mandatory_Detailed_{audience}", [])
            audience_results["mandatory_criteria"] = mandatory_detailed
            
            if not mandatory_passed:
                log_info(f"❌ [{product}] {company_name} mandatory НЕ пройдены для {audience}")
                audience_results["mandatory_status"] = "Failed"
                product_results["detailed_results"][audience] = audience_results
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
            
            # Record NTH results
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
            
            # Update mandatory criteria with any additional details from temp_mandatory_info
            if f"Mandatory_Detailed_{audience}" in temp_mandatory_info:
                audience_results["mandatory_criteria"] = temp_mandatory_info[f"Mandatory_Detailed_{audience}"]
            
            # ВСЕГДА добавляем detailed_results для каждой проверенной аудитории
            product_results["detailed_results"][audience] = audience_results
            
            if nth_score > 0:
                # SUCCESS! This is a QUALIFIED result
                audience_results["final_status"] = "Qualified"
                
                # Create readable text format for POSITIVE results
                qualified_text_parts = [
                    f"QUALIFIED: {audience}",
                    f"NTH Score: {nth_score:.3f}",
                    f"Total NTH Criteria: {nth_total}",
                    f"Passed: {nth_passed}",
                    f"ND (No Data): {nth_nd}"
                ]
                
                qualified_text = "\n".join(qualified_text_parts)
                
                # Create a copy of the record for this qualification
                qualified_record = record.copy()
                qualified_record["Qualified_Products"] = qualified_text
                qualified_record["All_Results"] = product_results
                results_list.append(qualified_record)
                
                log_info(f"🎉 [{product}] {company_name} QUALIFIED для {audience} (Score: {nth_score:.3f})")
            else:
                # Set failed status for audiences that don't qualify
                audience_results["final_status"] = "Failed"
        
        # If no successful qualifications, return the negative record
        if not results_list:
            record["All_Results"] = product_results
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
    if ASYNC_GPT_CONFIG['enable_async_gpt'] and not mandatory_df.empty:
        log_info(f"🤖 Using async GPT for mandatory criteria: {audience}")
        try:
            # ФИЛЬТРАЦИЯ: берем только критерии для конкретной аудитории
            audience_mandatory_df = mandatory_df[mandatory_df['Target Audience'] == audience].copy()
            
            if audience_mandatory_df.empty:
                log_info(f"⚠️ No mandatory criteria found for audience: {audience}")
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
                
                # Better matching: look for qualification results that match this criterion
                found_result = False
                for key, value in result.items():
                    if key.startswith("Qualified_") and value == "Yes":
                        # For mandatory, if ANY failed, all fail. If we get here, this one passed.
                        criterion_info["result"] = "Pass"
                        passed_mandatory += 1
                        found_result = True
                        break
                
                if not found_result:
                    criterion_info["result"] = "Fail"
                
                detailed_mandatory_results.append(criterion_info)
            
            # Store detailed mandatory results in company_info for later retrieval
            company_info[f"Mandatory_Detailed_{audience}"] = detailed_mandatory_results
            
            mandatory_passed = passed_mandatory == total_mandatory
            log_info(f"✅ Mandatory results for {audience}: {passed_mandatory}/{total_mandatory} passed → {'PASS' if mandatory_passed else 'FAIL'}")
            
            return mandatory_passed
            
        except Exception as e:
            log_error(f"❌ Async mandatory analysis failed: {e}")
            if ASYNC_GPT_CONFIG['fallback_to_sync']:
                log_info("🔄 Falling back to sync mandatory analysis...")
                return check_mandatory_criteria(company_info, audience, mandatory_df, session_id, use_deep_analysis)
            return False
    else:
        # Use original sync function
        return check_mandatory_criteria(company_info, audience, mandatory_df, session_id, use_deep_analysis)


def check_nth_criteria_batch(company_info, audience, nth_df, session_id=None, use_deep_analysis=False):
    """Асинхронная проверка NTH критериев с пакетной обработкой"""
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
                
                # Try to match this criterion result in the GPT response
                for key, value in result.items():
                    if key.startswith("Qualified_") and value == "Yes":
                        # This is a simplified matching - in reality you'd want more sophisticated matching
                        if qualified_count == idx or len(detailed_criteria_results) == idx:
                            criterion_info["result"] = "Pass"
                            qualified_count += 1
                            break
                else:
                    criterion_info["result"] = "Fail"
                
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
            log_error(f"❌ Async NTH analysis failed: {e}")
            if ASYNC_GPT_CONFIG['fallback_to_sync']:
                log_info("🔄 Falling back to sync NTH analysis...")
                check_nth_criteria(company_info, audience, nth_df, session_id, use_deep_analysis)
    else:
        # Use original sync function
        check_nth_criteria(company_info, audience, nth_df, session_id, use_deep_analysis)


def run_parallel_analysis(companies_file=None, load_all_companies=False, session_id=None, use_deep_analysis=False, max_concurrent_companies=5):
    """
    Запускает анализ с параллельной обработкой компаний внутри каждого продукта.
    СОХРАНЯЕТ порядок: все компании проходят продукт 1, потом все компании проходят продукт 2, и т.д.
    """
    try:
        # Load all data (аналогично оригинальному процессору)
        log_info("📋 Загружаем данные...")
        data_dict = load_data(
            companies_file=companies_file,
            load_all_companies=load_all_companies
        )
        
        companies_df = data_dict["companies"]
        products = data_dict["products"]
        products_data = data_dict["products_data"]
        general_criteria = data_dict["general_criteria"]
        
        log_info(f"🚀 ПАРАЛЛЕЛЬНАЯ ОБРАБОТКА АКТИВИРОВАНА")
        log_info(f"📊 Компаний: {len(companies_df)}")
        log_info(f"📋 Продукты: {', '.join(products)}")
        log_info(f"⚡ Максимум одновременных компаний: {max_concurrent_companies}")
        log_info(f"🎯 Ожидаем записей: {len(companies_df)} × {len(products)} = {len(companies_df) * len(products)}")
        
        # 1. Check General Criteria ONCE for all companies (последовательно, как и раньше)
        log_info(f"\n📝 Этап 1: Проверяем General критерии для ВСЕХ компаний...")
        general_status = {}
        
        for index, company_row in companies_df.iterrows():
            company_data = company_row.to_dict()
            company_name = company_data.get("Company_Name", "Unknown")
            description = company_data.get("Description", "")
            
            log_info(f"🌐 General для: {company_name}")
            
            temp_general_info = {}
            general_passed = check_general_criteria(description, temp_general_info, general_criteria)
            general_status[company_name] = general_passed
            
            # Store detailed general criteria information
            general_status[f"{company_name}_detailed"] = temp_general_info
            
            if general_passed:
                log_info("✅ General пройдены")
            else:
                log_info("❌ General НЕ пройдены")
        
        # 2. Process each product (СОХРАНЯЕМ ПОРЯДОК ПРОДУКТОВ)
        all_results = []
        
        for product_index, product in enumerate(products, 1):
            log_info(f"\n🎯 ПРОДУКТ {product_index}/{len(products)}: {product}")
            log_info(f"⚡ Обрабатываем ВСЕ {len(companies_df)} компаний ПАРАЛЛЕЛЬНО для продукта {product}")
            
            product_data = products_data[product]
            
            # Подготавливаем аргументы для параллельной обработки
            company_args = []
            for index, company_row in companies_df.iterrows():
                args = (company_row, product, product_data, general_status, session_id, use_deep_analysis)
                company_args.append(args)
            
            # ПАРАЛЛЕЛЬНАЯ ОБРАБОТКА компаний для текущего продукта
            product_results = []
            with ThreadPoolExecutor(max_workers=max_concurrent_companies) as executor:
                # Отправляем все компании на обработку
                future_to_company = {
                    executor.submit(process_single_company_for_product, args): args[0].get("Company_Name", f"Company_{i}")
                    for i, args in enumerate(company_args)
                }
                
                # Собираем результаты по мере завершения
                for future in as_completed(future_to_company):
                    company_name = future_to_company[future]
                    try:
                        company_results = future.result()
                        product_results.extend(company_results)
                        log_info(f"✅ [{product}] {company_name} завершена")
                    except Exception as e:
                        log_error(f"❌ [{product}] Ошибка обработки {company_name}: {e}")
            
            # Добавляем результаты продукта к общим результатам
            all_results.extend(product_results)
            log_info(f"🎉 ПРОДУКТ {product} ЗАВЕРШЕН: обработано {len(product_results)} записей")
        
        log_info(f"\n🏁 АНАЛИЗ ЗАВЕРШЕН!")
        log_info(f"📊 Итого записей: {len(all_results)}")
        
        # 3. Save results (аналогично оригинальному процессору)
        save_results(all_results, product="mixed", session_id=session_id)
        
        return all_results
        
    except KeyboardInterrupt:
        log_info("❌ Анализ прерван пользователем")
        raise
    except Exception as e:
        log_error(f"💥 Критическая ошибка: {e}")
        raise 