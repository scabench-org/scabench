#!/usr/bin/env python3
"""
Test runner for the scraper system
"""

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_all_tests():
    """Run all tests with detailed output"""
    
    # Create test loader
    loader = unittest.TestLoader()
    
    # Load all tests from test directory
    suite = loader.discover('test', pattern='test*.py')
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return exit code based on results
    return 0 if result.wasSuccessful() else 1


def run_specific_tests(test_module):
    """Run tests from a specific module"""
    
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(f'test.{test_module}')
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Run specific test module
        exit_code = run_specific_tests(sys.argv[1])
    else:
        # Run all tests
        print("Running all tests...")
        print("=" * 70)
        exit_code = run_all_tests()
        print("=" * 70)
        
        if exit_code == 0:
            print("✅ All tests passed!")
        else:
            print("❌ Some tests failed")
    
    sys.exit(exit_code)