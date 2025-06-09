"""
Модуль для форматирования результатов в JSON структуру
"""

import json
from typing import Dict, Any

def create_structured_output(company_results: Dict) -> Dict:
    """Create structured JSON output according to manager requirements"""
    
    # Extract company basic info
    company_name = company_results.get('Company_Name', 'Unknown')
    company_info = {
        'company_name': company_name,
        'website': company_results.get('Official_Website', ''),
        'description': company_results.get('Description', '')
    }
    
    # Extract general criteria results
    general_criteria = extract_general_criteria_results(company_results)
    
    # Extract qualification results
    qualification_results = extract_qualification_results(company_results)
    
    # Extract mandatory results
    mandatory_results = extract_mandatory_results(company_results)
    
    # Extract NTH results
    nth_results = extract_nth_results(company_results)
    
    # Generate scoring summary
    scoring_summary = generate_scoring_summary(mandatory_results, nth_results)
    
    # Create final structured output
    structured_output = {
        'company_info': company_info,
        'general_criteria': general_criteria,
        'qualification_results': qualification_results,
        'mandatory_results': mandatory_results,
        'nth_results': nth_results,
        'scoring_summary': scoring_summary,
        'metadata': {
            'total_criteria_checked': len(mandatory_results) + len(nth_results),
            'nd_count': count_nd_results(company_results)
        }
    }
    
    return structured_output

def extract_general_criteria_results(company_results):
    """Extract general criteria results"""
    status = company_results.get('Global_Criteria_Status', '')
    return {
        'passed': status == 'Passed',
        'status': status
    }

def extract_qualification_results(company_results):
    """Extract qualification results"""
    results = {}
    for key, value in company_results.items():
        if key.startswith('Qualification_'):
            audience = key.replace('Qualification_', '')
            results[audience] = {
                'result': value,
                'qualified': value.lower() == 'yes'
            }
    return results

def extract_mandatory_results(company_results):
    """Extract mandatory criteria results"""
    results = {}
    for key, value in company_results.items():
        if key.startswith('Mandatory_'):
            results[key] = value
    return results

def extract_nth_results(company_results):
    """Extract NTH criteria results"""
    results = {}
    for key, value in company_results.items():
        if key.startswith('NTH_'):
            results[key] = value
    return results

def generate_scoring_summary(mandatory_results, nth_results):
    """Generate scoring summary"""
    # Extract audience scores
    audiences = {}
    for key, value in nth_results.items():
        if key.startswith('NTH_Score_'):
            audience = key.replace('NTH_Score_', '')
            audiences[audience] = value
    
    # Determine overall status
    if not audiences:
        overall_status = "Not Qualified"
    elif any(score > 0.7 for score in audiences.values()):
        overall_status = "High Potential"
    elif any(score > 0.4 for score in audiences.values()):
        overall_status = "Medium Potential"
    else:
        overall_status = "Low Potential"
    
    return {
        'audiences': audiences,
        'overall_status': overall_status
    }

def count_nd_results(company_results):
    """Count ND results"""
    return sum(1 for value in company_results.values() if value == 'ND') 