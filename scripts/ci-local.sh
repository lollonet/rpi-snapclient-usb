#!/usr/bin/env bash
# Local CI runner - runs the same checks as GitHub Actions
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "Running Local CI Checks"
echo "========================================="
echo ""

# Color output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track failures
FAILED=0

# Function to run check
run_check() {
    local name="$1"
    local cmd="$2"

    echo -e "${YELLOW}▶ ${name}${NC}"
    if eval "$cmd"; then
        echo -e "${GREEN}✓ ${name} passed${NC}"
        echo ""
        return 0
    else
        echo -e "${RED}✗ ${name} failed${NC}"
        echo ""
        FAILED=$((FAILED + 1))
        return 1
    fi
}

# 1. Shellcheck
echo "========================================="
echo "1. LINT CHECKS"
echo "========================================="
echo ""

if command -v shellcheck &> /dev/null; then
    run_check "Shellcheck" "shellcheck common/scripts/*.sh" || true
else
    echo -e "${YELLOW}⚠ Shellcheck not installed (install: brew install shellcheck)${NC}"
    echo ""
fi

# 2. Hadolint
if command -v hadolint &> /dev/null; then
    run_check "Hadolint (snapclient)" "hadolint --config .hadolint.yaml common/docker/snapclient/Dockerfile" || true
    run_check "Hadolint (metadata)" "hadolint --config .hadolint.yaml digi-plus-4k/cover-display/Dockerfile" || true
else
    echo -e "${YELLOW}⚠ Hadolint not installed (install: brew install hadolint)${NC}"
    echo ""
fi

# 3. Test checks
echo "========================================="
echo "2. TEST CHECKS"
echo "========================================="
echo ""

run_check "Bash syntax (setup.sh)" "bash -n common/scripts/setup.sh" || true
run_check "HAT configurations" "bash tests/test-hat-configs.sh" || true
run_check "HAT config count" "test \$(ls -1 common/audio-hats/*.conf | wc -l | tr -d ' ') -eq 11" || true

# Summary
echo "========================================="
echo "SUMMARY"
echo "========================================="
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed! Ready to push.${NC}"
    exit 0
else
    echo -e "${RED}✗ ${FAILED} check(s) failed. Fix before pushing.${NC}"
    exit 1
fi
