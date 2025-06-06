#!/usr/bin/env python3
"""
Criteria evaluation for companies main script - обновлено согласно требованиям менеджера
"""

import time
from config import validate_config, PROCESSING_CONFIG
from data_utils import load_data, save_results
from json_formatter import create_structured_output, format_for_csv_output
from scoring_system import generate_scoring_summary
from logger_config import setup_logging, log_info, log_error, log_debug
from criteria_checkers import (
    check_general_criteria,
    check_qualification_questions,
    check_mandatory_criteria,
    check_nth_criteria
)

def process_company(company_row, data):
    """Process a single company according to correct algorithm sequence"""
    company = company_row.Company_Name
    description = company_row.Description
    
    # Extract website URL from company data if available
    website = getattr(company_row, 'Official_Website', '')
    
    log_info(f"\n🚀 Обработка компании: {company}")

    info = {
        "Company_Name": company,
        "Description": description,
        "Official_Website": website
    }

    # ШАГ 1: Check Global Criteria for given product based on gen_descr
    if data["general_criteria"]:
        if not check_general_criteria(description, info, data["general_criteria"]):
            info["Global_Criteria_Status"] = "Failed - Global criteria not passed"
            return info
        info["Global_Criteria_Status"] = "Passed"
    else:
        info["Global_Criteria_Status"] = "Skipped - No global criteria for this product"

    # ШАГ 2: Qualification Questions (based on gen_descr)
    if PROCESSING_CONFIG['use_general_desc_for_qualification']:
        check_qualification_questions(description, info, data["qualification_questions"])

    # ШАГ 3: Select Potential Products x Target Audiences
    qualified_audiences = []
    for audience in data["qualification_questions"]:
        q_col = f"Qualification_{audience}"
        if info.get(q_col, "").lower() == "yes":
            qualified_audiences.append(audience)
            log_info(f"✅ Квалифицирована для аудитории: {audience}")

    if not qualified_audiences:
        info["Final_Status"] = "Not qualified for any audience"
        return info

    # ШАГ 4-8: Process each qualified audience
    for audience in qualified_audiences:
        log_info(f"🎯 Обрабатываем аудиторию: {audience}")
        
        # ШАГ 4: Mandatory Criteria ('website' - check serper.dev)
        mandatory_passed = True
        if PROCESSING_CONFIG['use_serper_for_mandatory']:
            mandatory_passed = check_mandatory_criteria(description, info, audience, data["mandatory_df"])
        
        # ШАГ 6: if 4th point failed, exclude from further checks
        if not mandatory_passed:
            log_info(f"⛔ Компания исключена из аудитории {audience} - провал mandatory критериев")
            info[f"Status_{audience}"] = "Excluded - Mandatory criteria failed"
            continue  # Go to next audience, not next company
        
        info[f"Status_{audience}"] = "Passed mandatory criteria"
        
        # ШАГ 5: if passed or ND, then check Nice-To-Have Criteria (score)
        if data["nth_df"][data["nth_df"]["Target Audience"] == audience].shape[0] > 0:
            if PROCESSING_CONFIG['calculate_nth_scores']:
                check_nth_criteria(description, info, audience, data["nth_df"])

    # ШАГ 7-8: Product x TA = Score, Return score for each Product
    info["Final_Status"] = "Completed analysis"
    info["Qualified_Audiences"] = qualified_audiences
    
    return info

def process_industry(criteria_type, companies_data):
    """Process all companies for a specific industry sequentially"""
    log_info(f"\n🏭 Начинаем обработку отрасли: {criteria_type}")
    
    # Load data for this specific criteria type
    data = load_data()
    
    results = []
    log_info(f"\n📊 Начинаем анализ {len(companies_data)} компаний для {criteria_type}")
    
    # Process each company for this industry
    for row in companies_data.itertuples():
        result = process_company(row, data)
        
        # Create structured JSON output (новое требование)
        if PROCESSING_CONFIG['json_output_format']:
            structured_result = create_structured_output(result)
            csv_formatted = format_for_csv_output(structured_result, criteria_type)
            results.append(csv_formatted)
        else:
            results.append(result)
    
    return results

def main():
    """Main execution function - updated for manager requirements"""
    # Настройка логирования
    log_filename, file_logger = setup_logging()
    
    # Validate configuration
    validate_config()
    
    # Load companies data once
    from data_utils import load_companies_data
    companies_data = load_companies_data()
    
    log_info(f"\n🚀 Начинаем анализ {len(companies_data)} компаний")
    log_info(f"📋 Режим обработки: {'Последовательный' if PROCESSING_CONFIG['sequential_processing'] else 'Параллельный'}")
    
    # Sequential processing by industry (новое требование)
    if PROCESSING_CONFIG['sequential_processing']:
        from config import CRITERIA_TYPE
        
        # Process current criteria type
        results = process_industry(CRITERIA_TYPE, companies_data)
        
        # Save results with new format
        json_path, csv_path = save_results(results, CRITERIA_TYPE)
        
        log_info(f"\n🎉 Обработка завершена:")
        log_info(f"   Отрасль: {CRITERIA_TYPE}")
        log_info(f"   Обработано компаний: {len(results)}")
        log_info(f"   JSON результаты: {json_path}")
        log_info(f"   CSV результаты: {csv_path}")
        log_info(f"   Детальный лог: {log_filename}")
        
        return json_path, csv_path
    else:
        # Legacy single processing
        data = load_data()
        results = []
        for row in companies_data.itertuples():
            result = process_company(row, data)
            results.append(result)
        
        json_path, csv_path = save_results(results, data["product"])
        return json_path, csv_path

if __name__ == "__main__":
    main() 