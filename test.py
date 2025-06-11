import requests
r = requests.get('http://localhost:8000/api/criteria/files')
data = r.json()
print('Status:', r.status_code)
print('Files:', len(data['files']))
print('Products:', data['products']) 