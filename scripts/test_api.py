#!/usr/bin/env python3
"""
Script to test the Auction Houses API
This script will test all major endpoints and functionality
"""

import requests
import json
import time
from typing import Dict, Any
import sys
import os

# Add the backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

API_BASE_URL = "http://localhost:8000"
API_V1_URL = f"{API_BASE_URL}/api/v1"

class APITester:
    def __init__(self):
        self.results = []
        self.session = requests.Session()
        
    def log_test(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"   {details}")
        
        self.results.append({
            "test": test_name,
            "success": success,
            "details": details
        })
        
    def test_health_check(self):
        """Test basic health check endpoint"""
        try:
            response = self.session.get(f"{API_BASE_URL}/health")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                details = f"Status: {data.get('status')}, DB: {data.get('database')}"
            else:
                details = f"Status code: {response.status_code}"
                
            self.log_test("Health Check", success, details)
            return success
            
        except Exception as e:
            self.log_test("Health Check", False, f"Exception: {e}")
            return False
    
    def test_root_endpoint(self):
        """Test root endpoint"""
        try:
            response = self.session.get(API_BASE_URL)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                details = f"Message: {data.get('message')}"
            else:
                details = f"Status code: {response.status_code}"
                
            self.log_test("Root Endpoint", success, details)
            return success
            
        except Exception as e:
            self.log_test("Root Endpoint", False, f"Exception: {e}")
            return False
    
    def test_api_docs(self):
        """Test API documentation endpoint"""
        try:
            response = self.session.get(f"{API_BASE_URL}/docs")
            success = response.status_code == 200
            details = "API docs accessible" if success else f"Status: {response.status_code}"
            
            self.log_test("API Documentation", success, details)
            return success
            
        except Exception as e:
            self.log_test("API Documentation", False, f"Exception: {e}")
            return False
    
    def test_houses_endpoint(self):
        """Test auction houses endpoints"""
        try:
            # Test GET /houses/
            response = self.session.get(f"{API_V1_URL}/houses/")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                count = len(data) if isinstance(data, list) else 0
                details = f"Found {count} auction houses"
            else:
                details = f"Status code: {response.status_code}"
                
            self.log_test("GET /houses/", success, details)
            
            # Test with filters
            response = self.session.get(f"{API_V1_URL}/houses/?country=Colombia")
            filter_success = response.status_code == 200
            
            if filter_success:
                data = response.json()
                count = len(data) if isinstance(data, list) else 0
                details = f"Colombia filter returned {count} houses"
            else:
                details = f"Filter failed with status: {response.status_code}"
                
            self.log_test("GET /houses/ with filters", filter_success, details)
            
            return success and filter_success
            
        except Exception as e:
            self.log_test("Houses Endpoints", False, f"Exception: {e}")
            return False
    
    def test_specific_house(self):
        """Test specific house endpoint"""
        try:
            # Try to get house ID 1 (should be Bogotá Auctions)
            response = self.session.get(f"{API_V1_URL}/houses/1")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                details = f"House: {data.get('name')} ({data.get('country')})"
            else:
                details = f"Status code: {response.status_code}"
                
            self.log_test("GET /houses/1", success, details)
            
            # Test house stats
            if success:
                stats_response = self.session.get(f"{API_V1_URL}/houses/1/stats/")
                stats_success = stats_response.status_code == 200
                
                if stats_success:
                    stats_data = stats_response.json()
                    basic_stats = stats_data.get('basic_stats', {})
                    auctions = basic_stats.get('total_auctions', 0)
                    details = f"Stats loaded: {auctions} auctions"
                else:
                    details = f"Stats failed: {stats_response.status_code}"
                    
                self.log_test("GET /houses/1/stats/", stats_success, details)
                return success and stats_success
            
            return success
            
        except Exception as e:
            self.log_test("Specific House", False, f"Exception: {e}")
            return False
    
    def test_auctions_endpoint(self):
        """Test auctions endpoints"""
        try:
            # Test GET /auctions/
            response = self.session.get(f"{API_V1_URL}/auctions/")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                count = len(data) if isinstance(data, list) else 0
                details = f"Found {count} auctions"
            else:
                details = f"Status code: {response.status_code}"
                
            self.log_test("GET /auctions/", success, details)
            
            # Test with filters
            response = self.session.get(f"{API_V1_URL}/auctions/?status=upcoming")
            filter_success = response.status_code == 200
            
            if filter_success:
                data = response.json()
                count = len(data) if isinstance(data, list) else 0
                details = f"Upcoming filter returned {count} auctions"
            else:
                details = f"Filter failed: {response.status_code}"
                
            self.log_test("GET /auctions/ with filters", filter_success, details)
            
            return success and filter_success
            
        except Exception as e:
            self.log_test("Auctions Endpoints", False, f"Exception: {e}")
            return False
    
    def test_lots_endpoint(self):
        """Test lots endpoints"""
        try:
            # Test GET /lots/
            response = self.session.get(f"{API_V1_URL}/lots/")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                count = len(data) if isinstance(data, list) else 0
                details = f"Found {count} lots"
            else:
                details = f"Status code: {response.status_code}"
                
            self.log_test("GET /lots/", success, details)
            
            # Test search functionality
            search_response = self.session.get(f"{API_V1_URL}/lots/search/?q=pintura")
            search_success = search_response.status_code == 200
            
            if search_success:
                data = search_response.json()
                count = len(data) if isinstance(data, list) else 0
                details = f"Search returned {count} results"
            else:
                details = f"Search failed: {search_response.status_code}"
                
            self.log_test("GET /lots/search/", search_success, details)
            
            return success and search_success
            
        except Exception as e:
            self.log_test("Lots Endpoints", False, f"Exception: {e}")
            return False
    
    def test_artists_endpoint(self):
        """Test artists endpoints"""
        try:
            # Test GET /artists/
            response = self.session.get(f"{API_V1_URL}/artists/")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                count = len(data) if isinstance(data, list) else 0
                details = f"Found {count} artists"
            else:
                details = f"Status code: {response.status_code}"
                
            self.log_test("GET /artists/", success, details)
            
            # Test artist search
            search_response = self.session.get(f"{API_V1_URL}/artists/search/?q=Diego")
            search_success = search_response.status_code == 200
            
            if search_success:
                data = search_response.json()
                count = len(data) if isinstance(data, list) else 0
                details = f"Search returned {count} artists"
            else:
                details = f"Search failed: {search_response.status_code}"
                
            self.log_test("GET /artists/search/", search_success, details)
            
            return success and search_success
            
        except Exception as e:
            self.log_test("Artists Endpoints", False, f"Exception: {e}")
            return False
    
    def test_analytics_endpoint(self):
        """Test analytics endpoints"""
        try:
            # Test summary stats
            response = self.session.get(f"{API_V1_URL}/analytics/summary/")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                houses = data.get('total_houses', 0)
                auctions = data.get('total_auctions', 0)
                lots = data.get('total_lots', 0)
                details = f"{houses} houses, {auctions} auctions, {lots} lots"
            else:
                details = f"Status code: {response.status_code}"
                
            self.log_test("GET /analytics/summary/", success, details)
            
            # Test trends endpoint
            trends_response = self.session.get(f"{API_V1_URL}/analytics/trends/prices/")
            trends_success = trends_response.status_code == 200
            
            if trends_success:
                data = trends_response.json()
                count = len(data) if isinstance(data, list) else 0
                details = f"Price trends data: {count} series"
            else:
                details = f"Trends failed: {trends_response.status_code}"
                
            self.log_test("GET /analytics/trends/prices/", trends_success, details)
            
            return success and trends_success
            
        except Exception as e:
            self.log_test("Analytics Endpoints", False, f"Exception: {e}")
            return False
    
    def test_error_handling(self):
        """Test error handling for non-existent resources"""
        try:
            # Test non-existent house
            response = self.session.get(f"{API_V1_URL}/houses/999999")
            success = response.status_code == 404
            details = "Correctly returns 404 for non-existent house" if success else f"Unexpected status: {response.status_code}"
            
            self.log_test("Error Handling (404)", success, details)
            
            # Test malformed request
            malformed_response = self.session.get(f"{API_V1_URL}/lots/search/?q=a")  # Too short query
            malformed_success = malformed_response.status_code == 422  # Validation error
            details = "Correctly handles validation errors" if malformed_success else f"Status: {malformed_response.status_code}"
            
            self.log_test("Error Handling (Validation)", malformed_success, details)
            
            return success and malformed_success
            
        except Exception as e:
            self.log_test("Error Handling", False, f"Exception: {e}")
            return False
    
    def run_all_tests(self):
        """Run all API tests"""
        print("🧪 Starting API Tests")
        print("=" * 50)
        
        # Check if API is running
        try:
            response = self.session.get(API_BASE_URL, timeout=5)
            if response.status_code != 200:
                print(f"❌ API not accessible at {API_BASE_URL}")
                print("Please make sure the API is running with: make up-backend")
                return
        except Exception as e:
            print(f"❌ Cannot connect to API at {API_BASE_URL}")
            print(f"Error: {e}")
            print("Please make sure the API is running with: make up-backend")
            return
        
        # Run all tests
        tests = [
            self.test_health_check,
            self.test_root_endpoint,
            self.test_api_docs,
            self.test_houses_endpoint,
            self.test_specific_house,
            self.test_auctions_endpoint,
            self.test_lots_endpoint,
            self.test_artists_endpoint,
            self.test_analytics_endpoint,
            self.test_error_handling
        ]
        
        for test in tests:
            try:
                test()
            except Exception as e:
                self.log_test(test.__name__, False, f"Unexpected error: {e}")
            
            # Small delay between tests
            time.sleep(0.5)
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 50)
        print("📊 TEST SUMMARY")
        print("=" * 50)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for result in self.results if result['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ Failed Tests:")
            for result in self.results:
                if not result['success']:
                    print(f"   - {result['test']}: {result['details']}")
        
        print("\n" + "=" * 50)
        
        if passed_tests == total_tests:
            print("🎉 All tests passed! The API is working correctly.")
        else:
            print("⚠️  Some tests failed. Check the details above.")

def main():
    """Main function"""
    tester = APITester()
    tester.run_all_tests()

if __name__ == "__main__":
    main()