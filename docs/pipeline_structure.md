# Structure of pipeline_adapter.py Division

## 1. Main Modules

### `src/pipeline/`
Main directory for all pipeline files

### `src/pipeline/__init__.py`
Exports main public functions:
- `run_pipeline`
- `run_pipeline_for_file`

### `src/pipeline/adapter.py`
Contains the main `PipelineAdapter` class, which will replace most of pipeline_adapter.py and more conveniently manages state

### `src/pipeline/core.py`
Contains core process functions:
- `process_companies`
- `_process_single_company_async`

### `src/pipeline/utils/`
Directory for utility functions

### `src/pipeline/utils/markdown.py`
Contains functions for formatting and saving reports:
- `_generate_and_save_raw_markdown_report_async`

### `src/pipeline/utils/logging.py`
Contains logging setup functions:
- `setup_session_logging`

## 2. External Service Integrations

### `src/integrations/`
Root directory for different external integrations

### `src/integrations/hubspot/`
Directory for all HubSpot integration components

### `src/integrations/hubspot/client.py`
Contains the `HubSpotClient` class

### `src/integrations/hubspot/adapter.py`
Contains extension of the main pipeline:
- `HubSpotPipelineAdapter` class (inherits `PipelineAdapter`)

### `src/integrations/hubspot/service.py`
Contains integration logic:
- `HubSpotIntegrationService` class

## 3. Architecture and Interaction

1. `src/pipeline/adapter.py` contains the main pipeline functionality
2. `src/integrations/hubspot/adapter.py` inherits and extends the `PipelineAdapter` class
3. Entry point `run_pipeline` in `src/pipeline/__init__.py` selects the correct implementation based on configuration

## 4. Migration Algorithm

1. Create necessary directory structure
2. Move basic functionality to `src/pipeline/core.py` and `src/pipeline/utils/*.py`
3. Create `PipelineAdapter` class in `src/pipeline/adapter.py`
4. Move HubSpot integration to `src/integrations/hubspot/`
5. Create new entry point in `src/pipeline/__init__.py`
6. Update imports in existing code 