#!/bin/bash
# Enhanced run_tests.sh script for New England Listings project

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default settings
VERBOSE=0
COVERAGE=0
SKIP_SLOW=0
TEST_PATH="tests/"
OUTPUT_DIR="test_results"
SPECIFIC_TESTS=""
MARKERS=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -v|--verbose)
      VERBOSE=1
      shift
      ;;
    -c|--coverage)
      COVERAGE=1
      shift
      ;;
    -s|--skip-slow)
      SKIP_SLOW=1
      shift
      ;;
    -p|--path)
      TEST_PATH="$2"
      shift 2
      ;;
    -o|--output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    -t|--test)
      SPECIFIC_TESTS="$2"
      shift 2
      ;;
    -m|--marker)
      MARKERS="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  -v, --verbose         Enable verbose output"
      echo "  -c, --coverage        Run with coverage report"
      echo "  -s, --skip-slow       Skip slow tests (integration tests)"
      echo "  -p, --path PATH       Specify test path (default: tests/)"
      echo "  -o, --output-dir DIR  Specify output directory (default: test_results)"
      echo "  -t, --test PATTERN    Run specific tests (e.g., 'test_realtor' or 'test_utils/test_text.py')"
      echo "  -m, --marker MARKER   Run tests with specific marker (e.g., 'integration', 'performance', 'property')"      echo "  -h, --help            Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Create results directory
mkdir -p ${OUTPUT_DIR}

# Build pytest command
PYTEST_CMD="python -m pytest"

# Add verbosity
if [ $VERBOSE -eq 1 ]; then
  PYTEST_CMD="$PYTEST_CMD -v"
else
  PYTEST_CMD="$PYTEST_CMD -v --tb=short"
fi

# Skip slow tests if requested
if [ $SKIP_SLOW -eq 1 ]; then
  PYTEST_CMD="$PYTEST_CMD -k 'not slow'"
fi

# Add markers if specified
if [ ! -z "$MARKERS" ]; then
  PYTEST_CMD="$PYTEST_CMD -m $MARKERS"
fi

# Add specific tests if given
if [ ! -z "$SPECIFIC_TESTS" ]; then
  TEST_PATH="${TEST_PATH}/${SPECIFIC_TESTS}"
fi

# Add test path
PYTEST_CMD="$PYTEST_CMD $TEST_PATH"

# Run the tests
echo -e "${BLUE}Running tests...${NC}"
echo -e "${YELLOW}Command: $PYTEST_CMD${NC}"

echo -e "${BLUE}Test output will be saved to ${OUTPUT_DIR}/test_output.txt${NC}"
$PYTEST_CMD > ${OUTPUT_DIR}/test_output.txt 2>&1
TEST_EXIT_CODE=$?

# Run with coverage if requested
if [ $COVERAGE -eq 1 ]; then
  echo -e "${BLUE}Running tests with coverage...${NC}"
  COVERAGE_CMD="$PYTEST_CMD --cov=new_england_listings --cov-report=term-missing --cov-report=html:${OUTPUT_DIR}/htmlcov"
  echo -e "${YELLOW}Command: $COVERAGE_CMD${NC}"
  
  echo -e "${BLUE}Coverage report will be saved to ${OUTPUT_DIR}/coverage_report.txt${NC}"
  $COVERAGE_CMD > ${OUTPUT_DIR}/coverage_report.txt 2>&1
  COVERAGE_EXIT_CODE=$?
  
  # Generate HTML coverage report
  echo -e "${BLUE}HTML coverage report available at ${OUTPUT_DIR}/htmlcov/index.html${NC}"
fi

# Print test results summary
echo -e "\n${BLUE}==== Test Results Summary ====${NC}"

if [ $TEST_EXIT_CODE -eq 0 ]; then
  echo -e "${GREEN}All tests passed!${NC}"
else
  echo -e "${RED}Some tests failed.${NC}"
  echo -e "${YELLOW}Failed tests:${NC}"
  grep "FAILED" ${OUTPUT_DIR}/test_output.txt
fi

# Print some test statistics
TEST_COUNT=$(grep "collected " ${OUTPUT_DIR}/test_output.txt | grep -o "[0-9]* items" | grep -o "[0-9]*")
PASS_COUNT=$(grep "passed" ${OUTPUT_DIR}/test_output.txt | grep -o "[0-9]* passed" | grep -o "[0-9]*")
FAIL_COUNT=$(grep "failed" ${OUTPUT_DIR}/test_output.txt | grep -o "[0-9]* failed" | grep -o "[0-9]*")
SKIP_COUNT=$(grep "skipped" ${OUTPUT_DIR}/test_output.txt | grep -o "[0-9]* skipped" | grep -o "[0-9]*")

echo -e "${BLUE}Tests collected: ${TEST_COUNT:-0}${NC}"
echo -e "${GREEN}Tests passed: ${PASS_COUNT:-0}${NC}"
echo -e "${RED}Tests failed: ${FAIL_COUNT:-0}${NC}"
echo -e "${YELLOW}Tests skipped: ${SKIP_COUNT:-0}${NC}"

# Print coverage summary if run
if [ $COVERAGE -eq 1 ]; then
  echo -e "\n${BLUE}==== Coverage Summary ====${NC}"
  
  # Extract overall coverage percentage
  COVERAGE_PCT=$(grep "TOTAL" ${OUTPUT_DIR}/coverage_report.txt | awk '{print $NF}' | sed 's/%//')
  
  if [ -z "$COVERAGE_PCT" ]; then
    echo -e "${YELLOW}Could not determine coverage percentage.${NC}"
  else
    if (( $(echo "$COVERAGE_PCT >= 80" | bc -l) )); then
      echo -e "${GREEN}Overall coverage: $COVERAGE_PCT%${NC}"
    elif (( $(echo "$COVERAGE_PCT >= 60" | bc -l) )); then
      echo -e "${YELLOW}Overall coverage: $COVERAGE_PCT%${NC}"
    else
      echo -e "${RED}Overall coverage: $COVERAGE_PCT%${NC}"
    fi
  fi
  
  # List modules with low coverage
  echo -e "${YELLOW}Modules with low coverage:${NC}"
  grep -E "[0-9]+\%[ ]+[0-9]+[ ]+[0-9]+" ${OUTPUT_DIR}/coverage_report.txt | awk '$1 < 70 {print $0}' | sort -n
fi

# Return the test exit code
exit $TEST_EXIT_CODE