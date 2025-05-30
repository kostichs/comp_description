# 🔄 Clay Integration

## Endpoints
- **Sync**: `/api/clay/process-company` (30 sec timeout)
- **Async**: `/api/clay/process-company-async` (no timeouts)

## Clay Setup

### Sync variant
```
Method: POST
URL: https://aidoc-trigger.loca.lt/api/clay/process-company
Body: {
  "companyName": "{{ [Company Name] }}",
  "domain": "{{ [Domain] }}"
}
```

### Async variant
1. **HTTP API table**:
```
URL: https://aidoc-trigger.loca.lt/api/clay/process-company-async
Body: {
  "companyName": "{{ [Company Name] }}",
  "domain": "{{ [Domain] }}",
  "clay_webhook_url": "YOUR_WEBHOOK_URL"
}
```

2. **Webhook table**: automatically receives results

## Server startup
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 5000 --reload
lt --port 5000 --subdomain aidoc-trigger
```

## Key features
- HubSpot disabled for Clay (always full processing)
- Uses full LLM Deep Search algorithm
- Processing time: 30-180 seconds per company 