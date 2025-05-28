# HubSpot Environment Variables Setup

## Overview
The HubSpot integration now supports configurable base URLs through environment variables, allowing you to use different HubSpot portals without modifying the code.

## Required Environment Variables

### HUBSPOT_BASE_URL
This variable defines the base URL for HubSpot company record links.

**Format:** `https://app.hubspot.com/contacts/{PORTAL_ID}/record/0-2/`

**Default:** `https://app.hubspot.com/contacts/39585958/record/0-2/`

## How to Find Your Portal ID

1. Log into your HubSpot account
2. Navigate to any company record
3. Look at the URL in your browser address bar
4. The URL will look like: `https://app.hubspot.com/contacts/12345678/record/0-2/987654321`
5. The number after `/contacts/` is your Portal ID (e.g., `12345678`)

## Setting Up Your .env File

Create a `.env` file in your project root with the following content:

```env
# API Keys
OPENAI_API_KEY=your_openai_api_key_here
SERPER_API_KEY=your_serper_api_key_here
SCRAPINGBEE_API_KEY=your_scrapingbee_api_key_here
HUBSPOT_API_KEY=your_hubspot_api_key_here

# HubSpot Configuration
# Replace 12345678 with your actual Portal ID
HUBSPOT_BASE_URL=https://app.hubspot.com/contacts/12345678/record/0-2/

# Other Configuration
DEBUG=false
```

## How It Works

When the system generates CSV results, the `HubSpot_Company_ID` column will contain clickable links like:
- `https://app.hubspot.com/contacts/12345678/record/0-2/987654321`

Where:
- `12345678` is your Portal ID (from HUBSPOT_BASE_URL)
- `987654321` is the specific company ID in HubSpot

## Fallback Behavior

If `HUBSPOT_BASE_URL` is not set in your environment variables, the system will use the default Portal ID `39585958`.

## Testing

After setting up your environment variables, restart your application and process a few companies. Check the CSV output to ensure the HubSpot links are pointing to your correct portal. 