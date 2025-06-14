"""
Pytest configuration and shared fixtures
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from backend.main import app

@pytest.fixture(scope="session")
def client():
    """Test client for API endpoints"""
    return TestClient(app)

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def sample_csv_content():
    """Sample CSV content for testing file uploads"""
    return """Company Name,Website,Industry
Test Company 1,https://test1.com,Technology
Test Company 2,https://test2.com,Finance
Test Company 3,https://test3.com,Healthcare"""

@pytest.fixture
def sample_criteria_file():
    """Sample criteria file content"""
    return {
        "name": "test_criteria.json",
        "content": {
            "general_criteria": [
                {
                    "criteria_text": "Company has more than 100 employees",
                    "weight": 1.0
                }
            ],
            "products": {
                "AI": {
                    "qualification_criteria": [
                        {
                            "criteria_text": "Company uses artificial intelligence",
                            "weight": 1.0
                        }
                    ]
                }
            }
        }
    } 