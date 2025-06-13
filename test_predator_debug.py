from src.data_io import load_and_prepare_company_names

# Тестируем загрузку predator данных
result = load_and_prepare_company_names('test_predator_final.csv')
print("Результат загрузки:")
print(result)

if result:
    for i, company in enumerate(result):
        print(f"Компания {i+1}:")
        print(f"  name: {company.get('name')}")
        print(f"  url: {company.get('url')}")
        print(f"  predator: {company.get('predator')}")
        print(f"  status: {company.get('status')}")
        print() 