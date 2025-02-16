#!/bin/bash
# run_tests.sh

# Create results directory
mkdir -p test_results

# Run tests with detailed output
pytest tests/ -v --tb=short > test_results/test_output.txt 2>&1

# Run tests with coverage
pytest tests/ -v --cov=new_england_listings --cov-report=term-missing > test_results/coverage_report.txt 2>&1

# Print summary
echo "Test results saved to test_results/test_output.txt"
echo "Coverage report saved to test_results/coverage_report.txt"

# Print failed tests only
echo "Failed Tests:"
grep "FAILED" test_results/test_output.txt