"""
Главный процессор для анализа компаний по критериям
"""

import sys
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

def run_analysis(companies_file=None, load_all_companies=False, session_id=None, use_deep_analysis=False):
    """Run analysis: separate record for each company-product combination"""
    try:
        # Load all data
        log_info("Загружаем данные...")
        data_dict = load_data(
            companies_file=companies_file,
            load_all_companies=load_all_companies
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
        
        for index, company_row in companies_df.iterrows():
            company_data = company_row.to_dict()
            company_name = company_data.get("Company_Name", "Unknown")
            description = company_data.get("Description", "")
            
            log_info(f"General для: {company_name}")
            
            temp_general_info = {}
            general_passed = check_general_criteria(description, temp_general_info, general_criteria)
            general_status[company_name] = general_passed
            
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
                
                # Initialize results for this product
                product_results = {
                    "product": product,
                    "general_status": general_status.get(company_name, False),
                    "qualification_results": {},
                    "qualified_audiences": [],
                    "detailed_results": {}
                }
                
                # Check Qualification Questions for this product
                temp_qualification_info = {}
                if PROCESSING_CONFIG['use_general_desc_for_qualification']:
                    check_qualification_questions(description, temp_qualification_info, qualification_questions)
                
                # Record qualification results for ALL audiences
                for audience in qualification_questions.keys():
                    qualification_result = temp_qualification_info.get(f"Qualification_{audience}", "No")
                    product_results["qualification_results"][audience] = qualification_result
                    
                    if qualification_result == "Yes":
                        product_results["qualified_audiences"].append(audience)
                        log_info(f"Квалифицирована для {product}: {audience}")
                
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
                    
                    if not mandatory_passed:
                        log_info(f"Mandatory НЕ пройдены для {product} -> {audience}")
                        audience_results["mandatory_status"] = "Failed"
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
                    
                    audience_results["nth_results"] = {
                        "score": nth_score,
                        "total_criteria": nth_total,
                        "passed_criteria": nth_passed,
                        "nd_criteria": nth_nd,
                        "pass_rate": round(nth_passed / nth_total, 3) if nth_total > 0 else 0
                    }
                    
                    if nth_score > 0:
                        # SUCCESS! This is a QUALIFIED result
                        audience_results["final_status"] = "Qualified"
                        
                        # Create readable text format for POSITIVE results column
                        nth_details = []
                        for nth_key, nth_value in temp_nth_info.items():
                            if nth_key.startswith(f"NTH_{audience}_") and not nth_key.endswith(("_Score", "_Total", "_Passed", "_ND", "_ND_Rate")):
                                criteria_name = nth_key.replace(f"NTH_{audience}_", "")
                                nth_details.append(f"  • {criteria_name}: {nth_value}")
                        
                        # Create properly formatted text with line breaks for CSV
                        qualified_text_parts = [
                            f"QUALIFIED: {audience}",
                            f"NTH Score: {nth_score:.3f}",
                            f"Total NTH Criteria: {nth_total}",
                            f"Passed: {nth_passed}",
                            f"ND (No Data): {nth_nd}",
                            "NTH Results:"
                        ]
                        
                        # Add details on separate lines
                        if nth_details:
                            for detail in nth_details:
                                qualified_text_parts.append(detail.strip())
                        else:
                            qualified_text_parts.append("No detailed results available")
                        
                        # Join with actual line breaks for proper CSV formatting
                        qualified_text = "\n".join(qualified_text_parts)
                        
                        # If this is the first qualification for this record, replace default text
                        if record["Qualified_Products"] == "NOT QUALIFIED":
                            record["Qualified_Products"] = qualified_text
                        else:
                            # Append to existing qualifications with separator
                            record["Qualified_Products"] += f"\n\n=== SEPARATOR ===\n\n{qualified_text}"
                        
                        log_info(f"КВАЛИФИЦИРОВАНА: {product} -> {audience} (Score: {nth_score:.3f})")
                    else:
                        log_info(f"НЕ квалифицирована: {product} -> {audience} (Score: {nth_score:.3f})")
                    
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
        json_path, csv_path = save_results(all_results, "ALL_PRODUCTS", session_id=session_id)
        
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