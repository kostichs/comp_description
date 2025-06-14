#!/usr/bin/env python3
"""
Test Runner for Company Canvas Backend

Runs comprehensive test suite for all 25 API endpoints:
- 17 Criteria Analysis API endpoints
- 8 Descriptions Generation API endpoints
- Integration tests
- Performance tests
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"\n{'='*60}")
    print(f"🔄 {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False


def main():
    """Main test runner"""
    print("🧪 Company Canvas Backend Test Suite")
    print("Testing all 25 API endpoints after refactoring")
    
    # Ensure we're in the right directory
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Install test dependencies
    if not run_command("pip install -r requirements-test.txt", "Installing test dependencies"):
        print("❌ Failed to install test dependencies")
        return 1
    
    # Run different test categories
    test_commands = [
        ("pytest tests/test_criteria_api.py -v", "Testing Criteria API (17 endpoints)"),
        ("pytest tests/test_descriptions_api.py -v", "Testing Descriptions API (8 endpoints)"),
        ("pytest tests/test_integration.py -v", "Running Integration Tests"),
        ("pytest tests/ --cov=backend --cov-report=term-missing", "Full Test Suite with Coverage"),
    ]
    
    failed_tests = []
    
    for cmd, description in test_commands:
        if not run_command(cmd, description):
            failed_tests.append(description)
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 TEST SUMMARY")
    print(f"{'='*60}")
    
    if failed_tests:
        print(f"❌ {len(failed_tests)} test categories failed:")
        for test in failed_tests:
            print(f"   - {test}")
        return 1
    else:
        print("✅ All tests passed!")
        print("🎉 All 25 API endpoints are working correctly after refactoring!")
        return 0


if __name__ == "__main__":
    sys.exit(main()) 