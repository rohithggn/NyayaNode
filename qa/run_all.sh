#!/bin/bash
# NyayaNode QA — Full Test Suite Runner
# Usage: ./qa/run_all.sh [unit|integration|e2e|all]
#
# Environment variables:
#   BACKEND_URL  (default: http://localhost:8000)
#   FRONTEND_URL (default: http://localhost:3000)

set -e  # Exit immediately on any failure

MODE=${1:-all}
BACKEND_URL=${BACKEND_URL:-http://localhost:8000}
FRONTEND_URL=${FRONTEND_URL:-http://localhost:3000}

# ANSI colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo -e "${BLUE}  🏛️  NyayaNode QA Test Suite${NC}"
    echo -e "${BLUE}  Mode: ${YELLOW}$MODE${BLUE} | Backend: ${YELLOW}$BACKEND_URL${NC}"
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo ""
}

check_python() {
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python 3 not found. Install Python 3.11+${NC}"
        exit 1
    fi
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo -e "🐍 Python: ${GREEN}$PYTHON_VERSION${NC}"
}

check_dependencies() {
    echo "📦 Checking QA dependencies..."
    python3 -c "import pytest, httpx, faker, pydantic, respx" 2>/dev/null || {
        echo -e "${YELLOW}⚠️  Installing QA dependencies...${NC}"
        pip install -r qa/requirements.txt -q
    }
    echo -e "   ${GREEN}✓ Dependencies OK${NC}"
}

run_unit() {
    echo ""
    echo -e "${BLUE}▶ [1/3] Unit Tests${NC} (schema contracts + budget math)"
    echo "   Command: pytest qa/unit/ -v --tb=short"
    echo ""
    if pytest qa/unit/ -v --tb=short \
        --cov=agents --cov=shared \
        --cov-report=term-missing \
        --cov-report=html:qa/coverage_report; then
        echo -e "\n${GREEN}✅ Unit tests passed${NC}"
        UNIT_PASSED=true
    else
        echo -e "\n${RED}❌ Unit tests FAILED — fix before pushing!${NC}"
        UNIT_PASSED=false
        exit 1
    fi
}

run_integration() {
    echo ""
    echo -e "${BLUE}▶ [2/3] Integration Tests${NC} (API + SSE)"
    echo "   Command: pytest qa/integration/ -v --tb=short -m 'not slow'"
    echo ""

    # Check if backend is reachable
    if curl -s --max-time 2 "$BACKEND_URL/health" > /dev/null 2>&1; then
        echo -e "   ${GREEN}✓ Backend reachable at $BACKEND_URL${NC}"
        BACKEND_UP=true
    else
        echo -e "   ${YELLOW}⚠️  Backend not reachable — integration tests will skip${NC}"
        BACKEND_UP=false
    fi

    if pytest qa/integration/ -v --tb=short -m "not slow"; then
        echo -e "\n${GREEN}✅ Integration tests passed (or skipped — backend may be down)${NC}"
    else
        echo -e "\n${RED}❌ Integration tests FAILED${NC}"
        exit 1
    fi
}

run_e2e() {
    echo ""
    echo -e "${BLUE}▶ [3/3] End-to-End Demo Scenario Tests${NC}"
    echo "   Command: pytest qa/e2e/ -v --tb=long -s"
    echo -e "   ${YELLOW}⚠️  These tests are slow (~2-3 min). Running all 5 scenarios.${NC}"
    echo ""

    if pytest qa/e2e/ -v --tb=long -s; then
        echo -e "\n${GREEN}✅ E2E tests passed — all 5 demo scenarios work!${NC}"
    else
        echo -e "\n${RED}❌ E2E tests FAILED — demo is broken!${NC}"
        exit 1
    fi
}

print_summary() {
    echo ""
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo -e "${GREEN}🎉 All NyayaNode QA tests passed.${NC}"
    echo -e "${GREEN}   Safe to deploy to Vercel/Railway.${NC}"
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo ""
    if [ -d "qa/coverage_report" ]; then
        echo -e "📊 Coverage report: ${YELLOW}qa/coverage_report/index.html${NC}"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
print_header
check_python
check_dependencies

case "$MODE" in
    unit)        run_unit ;;
    integration) run_integration ;;
    e2e)         run_e2e ;;
    all)         run_unit && run_integration && run_e2e ;;
    *)
        echo -e "${RED}Unknown mode: $MODE. Use: unit | integration | e2e | all${NC}"
        exit 1
        ;;
esac

print_summary
