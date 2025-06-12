"""
Главный процессор для анализа компаний по критериям
"""

import sys
import asyncio
from pathlib import Path

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
from src.utils.config import PROCESSING_CONFIG, USE_SCRAPINGBEE_DEEP_ANALYSIS
from src.data.search_data_saver import initialize_search_data_saver, finalize_search_data_saving

async def process_company_all_products_async(company_data, products_data, general_criteria, session_id=None, use_deep_analysis=False):
    """
    Асинхронно обрабатывает одну компанию для всех продуктов
    """
    company_name = company_data.get("Company_Name", "Unknown")
    description = company_data.get("Description", "")
    
    log_info(f"🏢 Начинаем обработку компании: {company_name}")
    
    # 1. CHECK GENERAL CRITERIA ONCE (общие для всех продуктов)
    temp_general_info = {}
    general_passed = check_general_criteria(description, temp_general_info, general_criteria)
    
    log_info(f"  General критерии: {'✅ PASS' if general_passed else '❌ FAIL'}")
    
    # 2. PROCESS ALL PRODUCTS FOR THIS COMPANY
    company_results = []
    
    # Создаем асинхронные задачи для всех продуктов
    async def process_single_product(product_name, product_data):
        """Обрабатывает один продукт для компании"""
        try:
            log_info(f"  📦 {company_name} → {product_name}")
            
            # Create record for this company-product combination
            record = {
                **company_data,
                "Product": product_name,
                "All_Results": {},
                "Qualified_Products": "NOT QUALIFIED"
            }
            
            # Get detailed general results
            company_general_info = temp_general_info
            general_detailed = company_general_info.get("General_Detailed_Results", [])
            general_passed_count = company_general_info.get("General_Passed_Count", 0)
            general_total_count = company_general_info.get("General_Total_Count", len(general_criteria))
            
            # Initialize results for this product
            product_results = {
                "product": product_name,
                "general_status": general_passed,
                "general_criteria": {
                    "passed": general_passed,
                    "passed_count": general_passed_count,
                    "total_count": general_total_count,
                    "detailed_criteria": general_detailed
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
            
            # Record qualification results for ALL audiences with detailed info
            qualification_detailed = []
            for audience in qualification_questions.keys():
                qualification_result = temp_qualification_info.get(f"Qualification_{audience}", "No")
                product_results["qualification_results"][audience] = qualification_result
                
                qualification_detailed.append({
                    "audience": audience,
                    "question": qualification_questions[audience],
                    "result": qualification_result
                })
                
                if qualification_result == "Yes":
                    product_results["qualified_audiences"].append(audience)
                    log_info(f"    ✅ Квалифицирована для {audience}")
            
            # Store detailed qualification results
            product_results["qualification_criteria"] = qualification_detailed
            
            # If no qualified audiences, return early
            if not product_results["qualified_audiences"]:
                log_info(f"    ❌ Не квалифицирована для продукта {product_name}")
                record["All_Results"] = product_results
                return record
            
            # Process each qualified audience
            for audience in product_results["qualified_audiences"]:
                log_info(f"    🎯 Проверяем {audience}")
                
                # Initialize detailed results for this audience
                audience_results = {
                    "audience": audience,
                    "qualification_status": "Passed",
                    "mandatory_status": "Not Started",
                    "mandatory_criteria": [],
                    "nth_results": {},
                    "final_status": "Failed"
                }
                
                # Check Mandatory Criteria
                temp_mandatory_info = {
                    "Company_Name": company_data.get("Company_Name"),
                    "Official_Website": company_data.get("Official_Website"),
                    "Description": description
                }
                
                mandatory_passed = check_mandatory_criteria(
                    temp_mandatory_info, audience, product_data["mandatory_df"], 
                    session_id=session_id, use_deep_analysis=use_deep_analysis
                )
                
                # Collect detailed mandatory results
                mandatory_detailed = []
                mandatory_df = product_data["mandatory_df"]
                mandatory_criteria = mandatory_df[mandatory_df["Target Audience"] == audience]
                
                for _, row in mandatory_criteria.iterrows():
                    crit = row["Criteria"]
                    result = temp_mandatory_info.get(f"Mandatory_{audience}_{crit}", "Unknown")
                    mandatory_detailed.append({
                        "criteria_text": crit,
                        "result": result
                    })
                
                audience_results["mandatory_criteria"] = mandatory_detailed
                
                if not mandatory_passed:
                    log_info(f"    ❌ Mandatory НЕ пройдены для {audience}")
                    audience_results["mandatory_status"] = "Failed"
                    audience_results["final_status"] = "Failed Mandatory"
                    
                    # CREATE TEXT RESULT FOR FAILED MANDATORY
                    mandatory_details = []
                    for mandatory_result in mandatory_detailed:
                        criteria_text = mandatory_result["criteria_text"]
                        result = mandatory_result["result"]
                        mandatory_details.append(f"  • {criteria_text}: {result}")
                    
                    failed_text_parts = [
                        f"FAILED MANDATORY: {audience}",
                        f"Mandatory Status: Failed",
                        "Mandatory Results:"
                    ]
                    
                    if mandatory_details:
                        failed_text_parts.extend(mandatory_details)
                    else:
                        failed_text_parts.append("No detailed mandatory results available")
                    
                    failed_text = "\n".join(failed_text_parts)
                    
                    # Add to Qualified_Products column
                    if record["Qualified_Products"] == "NOT QUALIFIED":
                        record["Qualified_Products"] = failed_text
                    else:
                        record["Qualified_Products"] += f"\n\n=== SEPARATOR ===\n\n{failed_text}"
                    
                    product_results["detailed_results"][audience] = audience_results
                    continue
                
                log_info(f"    ✅ Mandatory пройдены для {audience}")
                audience_results["mandatory_status"] = "Passed"
                
                # Check NTH Criteria
                temp_nth_info = {
                    "Company_Name": company_data.get("Company_Name"),
                    "Official_Website": company_data.get("Official_Website"),
                    "Description": description
                }
                
                check_nth_criteria(
                    temp_nth_info, audience, product_data["nth_df"], 
                    session_id=session_id, use_deep_analysis=use_deep_analysis
                )
                
                # Record NTH results
                nth_score = temp_nth_info.get(f"NTH_Score_{audience}", 0)
                nth_total = temp_nth_info.get(f"NTH_Total_{audience}", 0)
                nth_passed = temp_nth_info.get(f"NTH_Passed_{audience}", 0)
                nth_nd = temp_nth_info.get(f"NTH_ND_{audience}", 0)
                
                # Collect detailed NTH results
                nth_detailed = []
                nth_df = product_data["nth_df"]
                nth_criteria = nth_df[nth_df["Target Audience"] == audience]
                
                for _, row in nth_criteria.iterrows():
                    crit = row["Criteria"]
                    result = temp_nth_info.get(f"NTH_{audience}_{crit}", "Unknown")
                    nth_detailed.append({
                        "criteria_text": crit,
                        "result": result
                    })
                
                audience_results["nth_results"] = {
                    "score": nth_score,
                    "total_criteria": nth_total,
                    "passed_criteria": nth_passed,
                    "nd_criteria": nth_nd,
                    "pass_rate": round(nth_passed / nth_total, 3) if nth_total > 0 else 0,
                    "detailed_criteria": nth_detailed
                }
                
                # SHOW ALL NTH RESULTS (regardless of score)
                # Set final status based on score
                if nth_score > 0:
                    audience_results["final_status"] = "Qualified"
                    status_label = "QUALIFIED"
                    log_info(f"    🎉 КВАЛИФИЦИРОВАНА для {audience} (Score: {nth_score:.3f})")
                else:
                    audience_results["final_status"] = "Completed - Zero Score"
                    status_label = "COMPLETED"
                    log_info(f"    ✅ Завершена обработка {audience} (Score: {nth_score:.3f})")
                
                # Create readable text format for ALL NTH results
                nth_details = []
                for nth_result in nth_detailed:
                    criteria_text = nth_result["criteria_text"]
                    result = nth_result["result"]
                    nth_details.append(f"  • {criteria_text}: {result}")
                
                # Create properly formatted text with line breaks for CSV
                result_text_parts = [
                    f"{status_label}: {audience}",
                    f"Mandatory Status: Passed",
                    f"NTH Score: {nth_score:.3f}",
                    f"Total NTH Criteria: {nth_total}",
                    f"Passed: {nth_passed}",
                    f"ND (No Data): {nth_nd}",
                    "NTH Results:"
                ]
                
                # Add details on separate lines
                if nth_details:
                    result_text_parts.extend(nth_details)
                else:
                    result_text_parts.append("No detailed NTH results available")
                
                # Join with actual line breaks for proper CSV formatting
                result_text = "\n".join(result_text_parts)
                
                # Add to Qualified_Products column
                if record["Qualified_Products"] == "NOT QUALIFIED":
                    record["Qualified_Products"] = result_text
                else:
                    record["Qualified_Products"] += f"\n\n=== SEPARATOR ===\n\n{result_text}"
                
                # Record detailed results
                product_results["detailed_results"][audience] = audience_results
            
            # Store ALL results for this product
            record["All_Results"] = product_results
            return record
            
        except Exception as e:
            log_error(f"❌ Ошибка обработки {company_name} для продукта {product_name}: {e}")
            error_record = {
                **company_data,
                "Product": product_name,
                "Qualified_Products": f"ERROR: {str(e)}",
                "All_Results": {"error": str(e)}
            }
            return error_record
    
    # Запускаем обработку всех продуктов параллельно
    try:
        # Создаем задачи для всех продуктов
        tasks = []
        for product_name, product_data in products_data.items():
            task = process_single_product(product_name, product_data)
            tasks.append(task)
        
        # Ждем завершения всех задач
        product_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        for result in product_results:
            if isinstance(result, Exception):
                log_error(f"❌ Ошибка при обработке продукта: {result}")
                # Создаем запись об ошибке
                error_record = {
                    **company_data,
                    "Product": "ERROR",
                    "Qualified_Products": f"ERROR: {str(result)}",
                    "All_Results": {"error": str(result)}
                }
                company_results.append(error_record)
            else:
                company_results.append(result)
        
        log_info(f"✅ Завершена обработка компании {company_name}: {len(company_results)} продуктов")
        return company_results
        
    except Exception as e:
        log_error(f"❌ Критическая ошибка при обработке {company_name}: {e}")
        # Возвращаем записи об ошибках для всех продуктов
        error_results = []
        for product_name in products_data.keys():
            error_record = {
                **company_data,
                "Product": product_name,
                "Qualified_Products": f"CRITICAL ERROR: {str(e)}",
                "All_Results": {"error": str(e)}
            }
            error_results.append(error_record)
        return error_results

async def run_analysis_optimized_async(companies_file=None, load_all_companies=False, session_id=None, use_deep_analysis=False, selected_products=None):
    """
    Оптимизированный анализ: каждая компания обрабатывается для всех продуктов асинхронно
    """
    try:
        # Initialize search data saver for this session
        if session_id:
            initialize_search_data_saver(session_id)
            log_info(f"🔧 Initialized search data saver for session: {session_id}")
        
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
        
        log_info(f"🏢 НОВЫЙ ОПТИМИЗИРОВАННЫЙ ПОРЯДОК: Каждая компания через все продукты")
        log_info(f"📊 Компаний: {len(companies_df)}")
        log_info(f"📦 Продукты: {', '.join(products)}")
        log_info(f"🎯 Ожидаем записей: {len(companies_df)} × {len(products)} = {len(companies_df) * len(products)}")
        
        all_results = []
        
        # Process each company for all products
        for index, company_row in companies_df.iterrows():
            company_data = company_row.to_dict()
            company_name = company_data.get("Company_Name", "Unknown")
            
            log_info(f"\n🏢 [{index+1}/{len(companies_df)}] Обрабатываем компанию: {company_name}")
            
            # Process this company for all products asynchronously
            company_results = await process_company_all_products_async(
                company_data, products_data, general_criteria, 
                session_id=session_id, use_deep_analysis=use_deep_analysis
            )
            
            # Add all results for this company
            all_results.extend(company_results)
            
            log_info(f"📈 Прогресс: {index+1}/{len(companies_df)} компаний обработано")
        
        # Count qualified companies
        qualified_count = sum(1 for result in all_results if result["Qualified_Products"] != "NOT QUALIFIED")
        
        # Save results
        log_info("💾 Сохраняем результаты...")
        json_path, csv_path = save_results(all_results, "OPTIMIZED_ALL_PRODUCTS", session_id=session_id, original_file_path=companies_file)
        
        # Finalize search data saving
        if session_id:
            saved_search_files = finalize_search_data_saving()
            log_info(f"📄 Saved search data files: {len(saved_search_files)}")
        
        log_info(f"""
🎉 Оптимизированная обработка завершена:
   📦 Продукты: {', '.join(products)}
   📊 Записей компания×продукт: {len(all_results)}
   ✅ Квалифицированных записей: {qualified_count}
   📄 JSON результаты: {json_path}
   📋 CSV результаты: {csv_path}""")
        
        return all_results
        
    except Exception as e:
        log_error(f"❌ Критическая ошибка оптимизированного анализа: {e}")
        raise

def run_analysis_optimized(companies_file=None, load_all_companies=False, session_id=None, use_deep_analysis=False, selected_products=None):
    """
    Синхронный wrapper для асинхронного оптимизированного анализа
    """
    return asyncio.run(run_analysis_optimized_async(
        companies_file=companies_file,
        load_all_companies=load_all_companies,
        session_id=session_id,
        use_deep_analysis=use_deep_analysis,
        selected_products=selected_products
    ))

async def run_analysis_super_optimized_async(companies_file=None, load_all_companies=False, session_id=None, use_deep_analysis=False, max_concurrent_companies=3, selected_products=None):
    """
    СУПЕР-оптимизированный анализ: обрабатывает несколько компаний одновременно + каждая компания асинхронно для всех продуктов
    """
    try:
        # Initialize search data saver for this session
        if session_id:
            initialize_search_data_saver(session_id)
            log_info(f"🔧 Initialized search data saver for session: {session_id}")
        
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
        
        log_info(f"🚀 СУПЕР-ОПТИМИЗИРОВАННЫЙ РЕЖИМ: {max_concurrent_companies} компаний параллельно")
        log_info(f"📊 Компаний: {len(companies_df)}")
        log_info(f"📦 Продукты: {', '.join(products)}")
        log_info(f"🎯 Ожидаем записей: {len(companies_df)} × {len(products)} = {len(companies_df) * len(products)}")
        
        all_results = []
        
        # Create semaphore to limit concurrent companies
        semaphore = asyncio.Semaphore(max_concurrent_companies)
        
        async def process_company_with_semaphore(company_data):
            """Обрабатывает компанию с контролем семафора"""
            async with semaphore:
                return await process_company_all_products_async(
                    company_data, products_data, general_criteria, 
                    session_id=session_id, use_deep_analysis=use_deep_analysis
                )
        
        # Create tasks for all companies
        tasks = []
        for index, company_row in companies_df.iterrows():
            company_data = company_row.to_dict()
            task = process_company_with_semaphore(company_data)
            tasks.append(task)
        
        log_info(f"🔥 Запускаем обработку {len(tasks)} компаний с лимитом {max_concurrent_companies} одновременно...")
        
        # Process all companies concurrently
        company_results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten all results
        for company_results in company_results_list:
            if isinstance(company_results, Exception):
                log_error(f"❌ Ошибка при обработке компании: {company_results}")
                # Skip failed companies
                continue
            else:
                all_results.extend(company_results)
        
        # Count qualified companies
        qualified_count = sum(1 for result in all_results if result["Qualified_Products"] != "NOT QUALIFIED")
        
        # Save results
        log_info("💾 Сохраняем результаты...")
        json_path, csv_path = save_results(all_results, "SUPER_OPTIMIZED_ALL_PRODUCTS", session_id=session_id, original_file_path=companies_file)
        
        # Finalize search data saving
        if session_id:
            saved_search_files = finalize_search_data_saving()
            log_info(f"📄 Saved search data files: {len(saved_search_files)}")
        
        log_info(f"""
🎉 СУПЕР-оптимизированная обработка завершена:
   📦 Продукты: {', '.join(products)}
   📊 Записей компания×продукт: {len(all_results)}
   ✅ Квалифицированных записей: {qualified_count}
   📄 JSON результаты: {json_path}
   📋 CSV результаты: {csv_path}
   ⚡ Параллельно обработано: {max_concurrent_companies} компаний одновременно""")
        
        return all_results
        
    except Exception as e:
        log_error(f"❌ Критическая ошибка супер-оптимизированного анализа: {e}")
        raise

def run_analysis_super_optimized(companies_file=None, load_all_companies=False, session_id=None, use_deep_analysis=False, max_concurrent_companies=3, selected_products=None):
    """
    Синхронный wrapper для супер-оптимизированного асинхронного анализа
    """
    return asyncio.run(run_analysis_super_optimized_async(
        companies_file=companies_file,
        load_all_companies=load_all_companies,
        session_id=session_id,
        use_deep_analysis=use_deep_analysis,
        max_concurrent_companies=max_concurrent_companies,
        selected_products=selected_products
    ))

def run_analysis(companies_file=None, load_all_companies=False, session_id=None, use_deep_analysis=False, selected_products=None):
    """Run analysis: separate record for each company-product combination"""
    try:
        # Initialize search data saver for this session
        if session_id:
            initialize_search_data_saver(session_id)
            log_info(f"🔧 Initialized search data saver for session: {session_id}")
        
        # Load all data
        log_info("Загружаем данные...")
        data_dict = load_data(
            companies_file=companies_file,
            load_all_companies=load_all_companies,
            selected_products=selected_products
        )
        
        companies_df = data_dict["companies"]
        products = data_dict["products"]
        products_data = data_dict["products_data"]
        general_criteria = data_dict["general_criteria"]
        
        log_info(f"ПРАВИЛЬНЫЙ ПОРЯДОК: Все компании через каждый продукт")
        log_info(f"Компаний: {len(companies_df)}")
        log_info(f"Продукты: {', '.join(products)}")
        log_info(f"Ожидаем записей: {len(companies_df)} × {len(products)} = {len(companies_df) * len(products)}")
        
        # 1. Check General Criteria ONCE for all companies
        log_info(f"\nЭтап 1: Проверяем General критерии для ВСЕХ компаний...")
        general_status = {}
        general_detailed_results = {}
        
        for index, company_row in companies_df.iterrows():
            company_data = company_row.to_dict()
            company_name = company_data.get("Company_Name", "Unknown")
            description = company_data.get("Description", "")
            
            log_info(f"General для: {company_name}")
            
            temp_general_info = {}
            general_passed = check_general_criteria(description, temp_general_info, general_criteria)
            general_status[company_name] = general_passed
            general_detailed_results[company_name] = temp_general_info
            
            if general_passed:
                log_info("General пройдены")
            else:
                log_info("General НЕ пройдены")
        
        # 2. Create separate record for each company-product combination
        all_results = []
        
        for product in products:
            log_info(f"\nЭтап 2: Обрабатываем ВСЕ компании через продукт {product}")
            
            product_data = products_data[product]
            qualification_questions = product_data["qualification_questions"]
            
            for index, company_row in companies_df.iterrows():
                company_data = company_row.to_dict()
                company_name = company_data.get("Company_Name", "Unknown")
                description = company_data.get("Description", "")
                
                log_info(f"\n{company_name} -> {product}")
                
                # Create SEPARATE record for this company-product combination
                record = {
                    **company_data,  # Исходные данные компании
                    "Product": product,  # Указываем для какого продукта эта запись
                    "All_Results": {},  # JSON с ВСЕМИ результатами (прошло + не прошло)
                    "Qualified_Products": "NOT QUALIFIED"  # По умолчанию негативный результат
                }
                
                # Get detailed general results if available
                company_general_info = general_detailed_results.get(company_name, {})
                general_detailed = company_general_info.get("General_Detailed_Results", [])
                general_passed_count = company_general_info.get("General_Passed_Count", 0)
                general_total_count = company_general_info.get("General_Total_Count", len(general_criteria))
                
                # Initialize results for this product
                product_results = {
                    "product": product,
                    "general_status": general_status.get(company_name, False),
                    "general_criteria": {
                        "passed": general_status.get(company_name, False),
                        "passed_count": general_passed_count,
                        "total_count": general_total_count,
                        "detailed_criteria": general_detailed
                    },
                    "qualification_results": {},
                    "qualified_audiences": [],
                    "detailed_results": {}
                }
                
                # Check Qualification Questions for this product
                temp_qualification_info = {}
                if PROCESSING_CONFIG['use_general_desc_for_qualification']:
                    check_qualification_questions(description, temp_qualification_info, qualification_questions)
                
                # Record qualification results for ALL audiences with detailed info
                qualification_detailed = []
                for audience in qualification_questions.keys():
                    qualification_result = temp_qualification_info.get(f"Qualification_{audience}", "No")
                    product_results["qualification_results"][audience] = qualification_result
                    
                    qualification_detailed.append({
                        "audience": audience,
                        "question": qualification_questions[audience],
                        "result": qualification_result
                    })
                    
                    if qualification_result == "Yes":
                        product_results["qualified_audiences"].append(audience)
                        log_info(f"Квалифицирована для {product}: {audience}")
                
                # Store detailed qualification results
                product_results["qualification_criteria"] = qualification_detailed
                
                # If no qualified audiences, record this in All_Results
                if not product_results["qualified_audiences"]:
                    log_info(f"Не квалифицирована для продукта {product}")
                    record["All_Results"] = product_results
                    all_results.append(record)
                    continue
                
                # Process each qualified audience
                for audience in product_results["qualified_audiences"]:
                    log_info(f"\nПроверяем {product} -> {audience}")
                    
                    # Initialize detailed results for this audience
                    audience_results = {
                        "audience": audience,
                        "qualification_status": "Passed",
                        "mandatory_status": "Not Started",
                        "mandatory_criteria": [],
                        "nth_results": {},
                        "final_status": "Failed"
                    }
                    
                    # Check Mandatory Criteria - передаем нужные данные из company_data
                    temp_mandatory_info = {
                        "Company_Name": company_data.get("Company_Name"),
                        "Official_Website": company_data.get("Official_Website"),
                        "Description": description
                    }
                    mandatory_passed = check_mandatory_criteria(temp_mandatory_info, audience, product_data["mandatory_df"], session_id=session_id, use_deep_analysis=use_deep_analysis)
                    
                    # Collect detailed mandatory results
                    mandatory_detailed = []
                    mandatory_df = product_data["mandatory_df"]
                    mandatory_criteria = mandatory_df[mandatory_df["Target Audience"] == audience]
                    
                    for _, row in mandatory_criteria.iterrows():
                        crit = row["Criteria"]
                        result = temp_mandatory_info.get(f"Mandatory_{audience}_{crit}", "Unknown")
                        mandatory_detailed.append({
                            "criteria_text": crit,
                            "result": result
                        })
                    
                    audience_results["mandatory_criteria"] = mandatory_detailed
                    
                    if not mandatory_passed:
                        log_info(f"Mandatory НЕ пройдены для {product} -> {audience}")
                        audience_results["mandatory_status"] = "Failed"
                        audience_results["final_status"] = "Failed Mandatory"
                        
                        # CREATE TEXT RESULT FOR FAILED MANDATORY
                        mandatory_details = []
                        for mandatory_result in mandatory_detailed:
                            criteria_text = mandatory_result["criteria_text"]
                            result = mandatory_result["result"]
                            mandatory_details.append(f"  • {criteria_text}: {result}")
                        
                        failed_text_parts = [
                            f"FAILED MANDATORY: {audience}",
                            f"Mandatory Status: Failed",
                            "Mandatory Results:"
                        ]
                        
                        if mandatory_details:
                            failed_text_parts.extend(mandatory_details)
                        else:
                            failed_text_parts.append("No detailed mandatory results available")
                        
                        failed_text = "\n".join(failed_text_parts)
                        
                        # Add to Qualified_Products column
                        if record["Qualified_Products"] == "NOT QUALIFIED":
                            record["Qualified_Products"] = failed_text
                        else:
                            record["Qualified_Products"] += f"\n\n=== SEPARATOR ===\n\n{failed_text}"
                        
                        product_results["detailed_results"][audience] = audience_results
                        continue
                    
                    log_info(f"Mandatory пройдены для {product} -> {audience}")
                    audience_results["mandatory_status"] = "Passed"
                    
                    # Check NTH Criteria - передаем нужные данные из company_data
                    temp_nth_info = {
                        "Company_Name": company_data.get("Company_Name"),
                        "Official_Website": company_data.get("Official_Website"),
                        "Description": description
                    }
                    check_nth_criteria(temp_nth_info, audience, product_data["nth_df"], session_id=session_id, use_deep_analysis=use_deep_analysis)
                    
                    # Record NTH results
                    nth_score = temp_nth_info.get(f"NTH_Score_{audience}", 0)
                    nth_total = temp_nth_info.get(f"NTH_Total_{audience}", 0)
                    nth_passed = temp_nth_info.get(f"NTH_Passed_{audience}", 0)
                    nth_nd = temp_nth_info.get(f"NTH_ND_{audience}", 0)
                    
                    # Collect detailed NTH results
                    nth_detailed = []
                    nth_df = product_data["nth_df"]
                    nth_criteria = nth_df[nth_df["Target Audience"] == audience]
                    
                    for _, row in nth_criteria.iterrows():
                        crit = row["Criteria"]
                        result = temp_nth_info.get(f"NTH_{audience}_{crit}", "Unknown")
                        nth_detailed.append({
                            "criteria_text": crit,
                            "result": result
                        })
                    
                    audience_results["nth_results"] = {
                        "score": nth_score,
                        "total_criteria": nth_total,
                        "passed_criteria": nth_passed,
                        "nd_criteria": nth_nd,
                        "pass_rate": round(nth_passed / nth_total, 3) if nth_total > 0 else 0,
                        "detailed_criteria": nth_detailed
                    }
                    
                    # SHOW ALL NTH RESULTS (regardless of score)
                    # Set final status based on score
                    if nth_score > 0:
                        audience_results["final_status"] = "Qualified"
                        status_label = "QUALIFIED"
                        log_info(f"КВАЛИФИЦИРОВАНА: {product} -> {audience} (Score: {nth_score:.3f})")
                    else:
                        audience_results["final_status"] = "Completed - Zero Score"
                        status_label = "COMPLETED"
                        log_info(f"Завершена обработка: {product} -> {audience} (Score: {nth_score:.3f})")
                    
                    # Create readable text format for ALL NTH results
                    nth_details = []
                    for nth_result in nth_detailed:
                        criteria_text = nth_result["criteria_text"]
                        result = nth_result["result"]
                        nth_details.append(f"  • {criteria_text}: {result}")
                    
                    # Create properly formatted text with line breaks for CSV
                    result_text_parts = [
                        f"{status_label}: {audience}",
                        f"Mandatory Status: Passed",
                        f"NTH Score: {nth_score:.3f}",
                        f"Total NTH Criteria: {nth_total}",
                        f"Passed: {nth_passed}",
                        f"ND (No Data): {nth_nd}",
                        "NTH Results:"
                    ]
                    
                    # Add details on separate lines
                    if nth_details:
                        result_text_parts.extend(nth_details)
                    else:
                        result_text_parts.append("No detailed NTH results available")
                    
                    # Join with actual line breaks for proper CSV formatting
                    result_text = "\n".join(result_text_parts)
                    
                    # Add to Qualified_Products column - ВСЕГДА ДОБАВЛЯЕМ ВСЕ РЕЗУЛЬТАТЫ
                    if record["Qualified_Products"] == "NOT QUALIFIED":
                        record["Qualified_Products"] = result_text
                    else:
                        record["Qualified_Products"] += f"\n\n{result_text}"
                    
                    # Record detailed results
                    product_results["detailed_results"][audience] = audience_results
                
                # Store ALL results for this product
                record["All_Results"] = product_results
                
                # Add record for this company-product combination
                all_results.append(record)
        
        # Count qualified companies
        qualified_count = sum(1 for result in all_results if result["Qualified_Products"])
        
        # Save results
        log_info("Сохраняем результаты...")
        json_path, csv_path = save_results(all_results, "ALL_PRODUCTS", session_id=session_id, original_file_path=companies_file)
        
        # Finalize search data saving
        if session_id:
            saved_search_files = finalize_search_data_saving()
            log_info(f"📄 Saved search data files: {len(saved_search_files)}")
        
        log_info(f"""
Обработка завершена:
   Продукты: {', '.join(products)}
   Записей компания×продукт: {len(all_results)}
   Квалифицированных записей: {qualified_count}
   JSON результаты: {json_path}
   CSV результаты: {csv_path}""")
        
        return all_results
        
    except Exception as e:
        log_error(f"Критическая ошибка анализа: {e}")
        raise 