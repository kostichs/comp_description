"""
Tests for Criteria Analysis API (17 endpoints)

Tests all endpoints in the criteria analysis system:
- Analysis endpoints (2)
- Session management (5) 
- Results retrieval (2)
- File management (7)
- Health check (1)
"""

import pytest
import json
import io
from fastapi import status


class TestCriteriaAnalysisEndpoints:
    """Test analysis endpoints"""
    
    def test_analyze_endpoint_get(self, client):
        """Test GET /api/criteria/analyze - should return 405 Method Not Allowed"""
        response = client.get("/api/criteria/analyze")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    
    def test_analyze_from_session_endpoint_get(self, client):
        """Test GET /api/criteria/analyze_from_session - should return 405 Method Not Allowed"""
        response = client.get("/api/criteria/analyze_from_session")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class TestCriteriaSessionEndpoints:
    """Test session management endpoints"""
    
    def test_get_sessions(self, client):
        """Test GET /api/criteria/sessions"""
        response = client.get("/api/criteria/sessions")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)
    
    def test_get_session_nonexistent(self, client):
        """Test GET /api/criteria/sessions/{id} with non-existent session"""
        response = client.get("/api/criteria/sessions/nonexistent_session")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()
    
    def test_get_session_status_nonexistent(self, client):
        """Test GET /api/criteria/sessions/{id}/status with non-existent session"""
        response = client.get("/api/criteria/sessions/nonexistent_session/status")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_get_session_progress_nonexistent(self, client):
        """Test GET /api/criteria/sessions/{id}/progress with non-existent session"""
        response = client.get("/api/criteria/sessions/nonexistent_session/progress")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_cancel_session_nonexistent(self, client):
        """Test POST /api/criteria/sessions/{id}/cancel with non-existent session"""
        response = client.post("/api/criteria/sessions/nonexistent_session/cancel")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestCriteriaResultsEndpoints:
    """Test results retrieval endpoints"""
    
    def test_get_session_results_nonexistent(self, client):
        """Test GET /api/criteria/sessions/{id}/results with non-existent session"""
        response = client.get("/api/criteria/sessions/nonexistent_session/results")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_download_session_results_nonexistent(self, client):
        """Test GET /api/criteria/sessions/{id}/download with non-existent session"""
        response = client.get("/api/criteria/sessions/nonexistent_session/download")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestCriteriaFileEndpoints:
    """Test file management endpoints"""
    
    def test_get_files(self, client):
        """Test GET /api/criteria/files"""
        response = client.get("/api/criteria/files")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "files" in data
        assert isinstance(data["files"], list)
    
    def test_get_file_nonexistent(self, client):
        """Test GET /api/criteria/files/{filename} with non-existent file"""
        response = client.get("/api/criteria/files/nonexistent_file.json")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_update_file_nonexistent(self, client, sample_criteria_file):
        """Test PUT /api/criteria/files/{filename} with non-existent file"""
        response = client.put(
            "/api/criteria/files/nonexistent_file.json",
            json=sample_criteria_file["content"]
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_create_file_invalid_data(self, client):
        """Test POST /api/criteria/files with invalid data"""
        response = client.post("/api/criteria/files", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_upload_file_no_file(self, client):
        """Test POST /api/criteria/upload without file"""
        response = client.post("/api/criteria/upload")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_upload_file_invalid_format(self, client):
        """Test POST /api/criteria/upload with invalid file format"""
        files = {"file": ("test.txt", "invalid content", "text/plain")}
        response = client.post("/api/criteria/upload", files=files)
        # Should either accept and process or reject with appropriate error
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]
    
    def test_delete_file_nonexistent(self, client):
        """Test DELETE /api/criteria/files/{filename} with non-existent file"""
        response = client.delete("/api/criteria/files/nonexistent_file.json")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestCriteriaHealthEndpoint:
    """Test health check endpoint"""
    
    def test_health_check(self, client):
        """Test GET /api/criteria/health"""
        response = client.get("/api/criteria/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "service" in data
        assert "status" in data
        assert data["service"] == "criteria_analysis"
        assert data["status"] == "healthy"


class TestCriteriaIntegrationScenarios:
    """Integration test scenarios"""
    
    def test_full_workflow_simulation(self, client, sample_csv_content):
        """Test a complete workflow simulation"""
        # 1. Check health
        health_response = client.get("/api/criteria/health")
        assert health_response.status_code == status.HTTP_200_OK
        
        # 2. Get available files
        files_response = client.get("/api/criteria/files")
        assert files_response.status_code == status.HTTP_200_OK
        
        # 3. Get sessions
        sessions_response = client.get("/api/criteria/sessions")
        assert sessions_response.status_code == status.HTTP_200_OK
        
        # All basic endpoints should be accessible
        assert all(r.status_code == status.HTTP_200_OK for r in [health_response, files_response, sessions_response])


# Test existing sessions if any are loaded
class TestCriteriaExistingSessions:
    """Test with existing sessions loaded from filesystem"""
    
    def test_existing_sessions_accessible(self, client):
        """Test that existing sessions are accessible"""
        response = client.get("/api/criteria/sessions")
        assert response.status_code == status.HTTP_200_OK
        sessions = response.json()
        
        # If sessions exist, test accessing them
        for session in sessions[:3]:  # Test first 3 sessions
            session_id = session.get("session_id")
            if session_id:
                # Test session details
                detail_response = client.get(f"/api/criteria/sessions/{session_id}")
                assert detail_response.status_code == status.HTTP_200_OK
                
                # Test session status
                status_response = client.get(f"/api/criteria/sessions/{session_id}/status")
                assert status_response.status_code == status.HTTP_200_OK
                
                # Test session progress
                progress_response = client.get(f"/api/criteria/sessions/{session_id}/progress")
                assert progress_response.status_code == status.HTTP_200_OK 