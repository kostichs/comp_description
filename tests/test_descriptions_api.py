"""
Tests for Descriptions Generation API (8 endpoints)

Tests all endpoints in the descriptions generation system:
- Session management (3)
- Processing control (2) 
- Results retrieval (3)
"""

import pytest
import json
import io
from fastapi import status


class TestDescriptionsSessionEndpoints:
    """Test session management endpoints"""
    
    def test_get_sessions(self, client):
        """Test GET /api/descriptions/"""
        response = client.get("/api/descriptions/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Descriptions API returns sessions directly as a list
        assert isinstance(data, list)
    
    def test_create_session_no_file(self, client):
        """Test POST /api/descriptions/create without file"""
        response = client.post("/api/descriptions/create")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_get_session_nonexistent(self, client):
        """Test GET /api/descriptions/{id} with non-existent session"""
        response = client.get("/api/descriptions/nonexistent_session")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDescriptionsProcessingEndpoints:
    """Test processing control endpoints"""
    
    def test_start_processing_nonexistent(self, client):
        """Test POST /api/descriptions/{id}/start with non-existent session"""
        response = client.post("/api/descriptions/nonexistent_session/start")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_cancel_processing_nonexistent(self, client):
        """Test POST /api/descriptions/{id}/cancel with non-existent session"""
        response = client.post("/api/descriptions/nonexistent_session/cancel")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDescriptionsResultsEndpoints:
    """Test results retrieval endpoints"""
    
    def test_get_session_results_nonexistent(self, client):
        """Test GET /api/descriptions/{id}/results with non-existent session"""
        response = client.get("/api/descriptions/nonexistent_session/results")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_download_session_results_nonexistent(self, client):
        """Test GET /api/descriptions/{id}/download with non-existent session"""
        response = client.get("/api/descriptions/nonexistent_session/download")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_get_session_logs_nonexistent(self, client):
        """Test GET /api/descriptions/{id}/logs with non-existent session"""
        response = client.get("/api/descriptions/nonexistent_session/logs")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDescriptionsIntegrationScenarios:
    """Integration test scenarios"""
    
    def test_full_workflow_simulation(self, client, sample_csv_content):
        """Test a complete workflow simulation"""
        # 1. Get sessions list
        sessions_response = client.get("/api/descriptions/")
        assert sessions_response.status_code == status.HTTP_200_OK
        
        # 2. Try to create session with invalid data (should fail gracefully)
        create_response = client.post("/api/descriptions/create")
        assert create_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Basic endpoints should be accessible
        assert sessions_response.status_code == status.HTTP_200_OK


class TestDescriptionsExistingSessions:
    """Test with existing sessions loaded from filesystem"""
    
    def test_existing_sessions_accessible(self, client):
        """Test that existing sessions are accessible"""
        response = client.get("/api/descriptions/")
        assert response.status_code == status.HTTP_200_OK
        sessions = response.json()  # Direct list, not wrapped in object
        
        # If sessions exist, test accessing them
        for session in sessions[:3]:  # Test first 3 sessions
            session_id = session.get("session_id")
            if session_id:
                # Test session details
                detail_response = client.get(f"/api/descriptions/{session_id}")
                assert detail_response.status_code == status.HTTP_200_OK
                
                # Test session results (might be 404 if no results yet)
                results_response = client.get(f"/api/descriptions/{session_id}/results")
                assert results_response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]


class TestDescriptionsFileUpload:
    """Test file upload functionality"""
    
    def test_create_session_with_valid_csv(self, client, sample_csv_content):
        """Test POST /api/descriptions/create with valid CSV"""
        files = {"file": ("test.csv", sample_csv_content, "text/csv")}
        data = {
            "use_hubspot": "false",
            "use_predator": "false"
        }
        
        response = client.post("/api/descriptions/create", files=files, data=data)
        # Should either succeed or fail with specific validation error
        assert response.status_code in [
            status.HTTP_200_OK, 
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ]
    
    def test_create_session_with_invalid_file(self, client):
        """Test POST /api/descriptions/create with invalid file"""
        files = {"file": ("test.txt", "invalid content", "text/plain")}
        data = {
            "use_hubspot": "false",
            "use_predator": "false"
        }
        
        response = client.post("/api/descriptions/create", files=files, data=data)
        # Should reject invalid file format
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ] 