# Company Canvas Deployment Summary

## Latest Version: v10 ✅

### Quick Deployment (Current Version)
```bash
# Stop old version
docker stop company-canvas-prod && docker rm company-canvas-prod

# Pull and start v10
docker pull sergeykostichev/company-canvas-app:v10

docker run -d --restart unless-stopped --name company-canvas-prod -p 80:8000 \
  -e OPENAI_API_KEY="YOUR_KEY" \
  -e SERPER_API_KEY="YOUR_KEY" \
  -e SCRAPINGBEE_API_KEY="YOUR_KEY" \
  -e HUBSPOT_API_KEY="YOUR_KEY" \
  -e HUBSPOT_BASE_URL="https://app.hubspot.com/contacts/YOUR_PORTAL_ID/record/0-2/" \
  -v /srv/company-canvas/output:/app/output \
  -v /srv/company-canvas/sessions_metadata.json:/app/sessions_metadata.json \
  sergeykostichev/company-canvas-app:v10
```

## Version History

### v10 (Current) - Results Display & Session Sync Fixes
**Released:** December 2024
**Key Changes:**
- 🎯 **FIXED:** Results display logic - ALL completed NTH analyses now appear in "All Results"
- 🎯 **FIXED:** Zero NTH score results show full analysis data instead of "NOT QUALIFIED"  
- 🔄 **FIXED:** Auto-refresh of latest session info on criteria tab after completion
- 📊 **IMPROVED:** Clear distinction between failed qualification/mandatory vs completed analysis
- ⚖️ **ENHANCED:** Performance optimizations with balanced API rate limiting

**Critical Bug Fixes:**
- Companies reaching NTH analysis stage (even with 0 score) now display complete results
- Latest session automatically updates on second tab without manual refresh (F5)
- Proper categorization: fail before NTH = "NOT QUALIFIED", complete NTH = full results

### v09 - Performance Optimizations
**Key Changes:**
- Balanced API rate limiting (speed vs stability)
- URL validation optimization (0.2s delay)
- ScrapingBee concurrency improvements
- Batch size standardization to 5

### v08 - Result Validation System
**Key Changes:**
- LLM-based validation to prevent unrelated company information
- Person name vs company name detection
- New CSV fields: validation_status, validation_warning
- Prevents irrelevant data like personal GitHub profiles

### v07 - Criteria Analysis Enhancement
**Key Changes:**
- Added deep analysis mode for criteria processing
- Parallel processing improvements
- Enhanced error handling

## Current Status
- ✅ **Performance:** ~3 companies per minute (balanced settings)
- ✅ **Stability:** API rate limiting protections in place
- ✅ **UI/UX:** Auto-updating session info, complete results display
- ✅ **Validation:** LLM-powered result verification
- ✅ **Criteria Analysis:** Full parallel processing with detailed results

## Validation Checklist for v10
After deployment, verify:

1. **Results Display:**
   - [ ] Companies with 0 NTH score show full analysis (not "NOT QUALIFIED")
   - [ ] Failed qualification/mandatory show "NOT QUALIFIED" with reason
   - [ ] All completed analyses appear in "All Results" column

2. **Session Sync:**
   - [ ] Process companies on first tab
   - [ ] Latest session info auto-updates on second tab (no F5 needed)
   - [ ] "Use results from latest session" checkbox gets new data

3. **Performance:**
   - [ ] Processing speed around 3 companies per minute
   - [ ] No API rate limiting errors in logs
   - [ ] Stable operation during long sessions

## Common Issues & Solutions

### Issue: Zero score results don't appear
**Solution:** Check v10 deployment - this was the main fix

### Issue: Latest session not updating automatically  
**Solution:** Check v10 deployment - auto-refresh was added

### Issue: Performance degradation
**Solution:** Check API keys, monitor logs for rate limiting

### Issue: Container won't start
**Solution:** 
```bash
# Check logs
docker logs company-canvas-prod

# Common fixes
sudo mkdir -p /srv/company-canvas/output
echo '[]' > /srv/company-canvas/sessions_metadata.json
chmod 666 /srv/company-canvas/sessions_metadata.json
```

## Monitoring Commands
```bash
# Check container status
docker ps

# View logs
docker logs company-canvas-prod

# Real-time logs
docker logs -f company-canvas-prod

# Check resource usage
docker stats company-canvas-prod
```

## Rollback (if needed)
```bash
# Rollback to previous stable version
docker stop company-canvas-prod && docker rm company-canvas-prod
docker run -d --restart unless-stopped --name company-canvas-prod -p 80:8000 \
  [same environment variables and volumes] \
  sergeykostichev/company-canvas-app:v09
```

## Next Version Planning: v11
Potential improvements:
- Real-time WebSocket updates for session progress
- Advanced analytics dashboard
- Batch processing queue management
- Enhanced criteria management interface 