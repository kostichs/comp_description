"""
Integration Tests

Tests cross-API functionality and end-to-end workflows:
- API health checks
- Cross-service communication
- Performance tests
- Error handling
"""

import pytest
import time
from fastapi import status


class TestAPIHealth:
    """Test overall API health and availability"""
    
    def test_all_api_health_endpoints(self, client):
        """Test all health check endpoints are accessible"""
        endpoints = [
            "/api/criteria/health",
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "status" in data
            assert data["status"] == "healthy"
    
    def test_api_response_times(self, client):
        """Test API response times are reasonable"""
        endpoints = [
            "/api/criteria/health",
            "/api/criteria/sessions",
            "/api/criteria/files",
            "/api/descriptions/",
        ]
        
        for endpoint in endpoints:
            start_time = time.time()
            response = client.get(endpoint)
            end_time = time.time()
            
            response_time = end_time - start_time
            assert response.status_code == status.HTTP_200_OK
            assert response_time < 5.0  # Should respond within 5 seconds


class TestCrossAPIFunctionality:
    """Test functionality that spans multiple APIs"""
    
    def test_session_data_consistency(self, client):
        """Test that session data is consistent across APIs"""
        # Get criteria sessions
        criteria_response = client.get("/api/criteria/sessions")
        assert criteria_response.status_code == status.HTTP_200_OK
        
        # Get descriptions sessions
        descriptions_response = client.get("/api/descriptions/")
        assert descriptions_response.status_code == status.HTTP_200_OK
        
        # Both should return valid data structures
        criteria_sessions = criteria_response.json()
        descriptions_data = descriptions_response.json()
        
        assert isinstance(criteria_sessions, list)
        assert isinstance(descriptions_data.get("sessions", []), list)


class TestErrorHandling:
    """Test error handling across all APIs"""
    
    def test_404_errors_consistent(self, client):
        """Test that 404 errors are handled consistently"""
        endpoints_404 = [
            "/api/criteria/sessions/nonexistent",
            "/api/criteria/files/nonexistent.json",
            "/api/descriptions/nonexistent",
        ]
        
        for endpoint in endpoints_404:
            response = client.get(endpoint)
            assert response.status_code == status.HTTP_404_NOT_FOUND
            data = response.json()
            assert "detail" in data
    
    def test_405_errors_consistent(self, client):
        """Test that 405 errors are handled consistently for wrong methods"""
        endpoints_405 = [
            ("/api/criteria/analyze", "GET"),  # Should be POST
            ("/api/descriptions/create", "GET"),  # Should be POST
        ]
        
        for endpoint, method in endpoints_405:
            if method == "GET":
                response = client.get(endpoint)
            elif method == "POST":
                response = client.post(endpoint)
            
            assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class TestDataValidation:
    """Test data validation across APIs"""
    
    def test_invalid_json_handling(self, client):
        """Test handling of invalid JSON data"""
        endpoints = [
            "/api/criteria/files",
        ]
        
        for endpoint in endpoints:
            # Send invalid JSON
            response = client.post(
                endpoint,
                data="invalid json",
                headers={"Content-Type": "application/json"}
            )
            # Should handle gracefully
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ]


class TestPerformance:
    """Basic performance tests"""
    
    def test_concurrent_requests(self, client):
        """Test handling of multiple concurrent requests"""
        import concurrent.futures
        import threading
        
        def make_request():
            return client.get("/api/criteria/health")
        
        # Make 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        for response in results:
            assert response.status_code == status.HTTP_200_OK
    
    def test_large_session_list_performance(self, client):
        """Test performance with large session lists"""
        start_time = time.time()
        
        # Get sessions from both APIs
        criteria_response = client.get("/api/criteria/sessions")
        descriptions_response = client.get("/api/descriptions/")
        
        end_time = time.time()
        
        assert criteria_response.status_code == status.HTTP_200_OK
        assert descriptions_response.status_code == status.HTTP_200_OK
        
        # Should complete within reasonable time even with many sessions
        total_time = end_time - start_time
        assert total_time < 10.0  # Should complete within 10 seconds 