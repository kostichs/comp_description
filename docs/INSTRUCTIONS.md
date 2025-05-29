# Instructions for Running the Company Information Search System

## 1. Stopping Previous Processes

In Windows, execute the following commands to stop previous processes:

```
taskkill /F /IM python.exe
```

Or use Task Manager (Ctrl+Shift+Esc), find Python processes and terminate them manually.

## 2. Running the Backend

Open the first terminal in the project root directory:

```
cd D:\PyProjects\company-description
python -m uvicorn backend.main:app --reload
```

The backend will be available at: http://127.0.0.1:8000

<!-- ## 3. Running the Frontend

Open the second terminal in the project root directory:

```
cd D:\PyProjects\company-description
python -m http.server 8001 --directory frontend
```

The frontend will be available at: http://localhost:8001

## 4. Using the System -->

## 3. Using the System

1. Open a web browser and go to: http://localhost:8000
2. Upload a CSV/Excel file with a list of companies
3. If necessary, specify additional context
4. Select search methods (standard and/or LLM Deep Search)
5. Click the "Start Processing" button
6. Wait for processing to complete
7. View and download results

## 4. Input File Formats

The system supports two input file formats:

### 4.1. Single Column File (Company Names)

Example CSV file:
```
Company Name
Microsoft
Google
Apple
```

In this mode, the system will perform full research, including finding the company's official website.

### 4.2. Two Column File (Company Names and Official Website URLs)

Example CSV file:
```
Company Name,Official Website
Microsoft,https://microsoft.com
Google,https://google.com
Apple,https://apple.com
```

In this mode, the system will use the provided URLs as official websites and will not search for them. This simplifies and speeds up the information gathering process.

The system automatically detects the input file format and selects the appropriate operating mode.

## 5. System Structure

The system uses a modular architecture:
- Finders for information search (LinkedInFinder, LLMDeepSearchFinder)
- Description generator (DescriptionGenerator)
- Adapter for web interface integration (pipeline_adapter.py)

Work results are saved to CSV files in the sessions directory. 