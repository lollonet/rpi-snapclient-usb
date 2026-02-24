#!/usr/bin/env bash
set -euo pipefail

# Test MIXER validation logic from entrypoint.sh
# Runs the validation block in isolation without exec'ing snapclient.

pass=0
fail=0

# Write the validation logic to a temp file (avoids quoting issues)
VALIDATOR=$(mktemp)
trap 'rm -f "$VALIDATOR"' EXIT

cat > "$VALIDATOR" << 'VALIDATION'
#!/bin/sh
MIXER="${MIXER:-software}"
validate_string() {
    case "$1" in
        *[\'\"\\$\`\;\&\|\>\<\(\)\{\}\[\]]*)
            echo "REJECTED"
            exit 1
            ;;
    esac
}
MIXER_MODE="${MIXER%%:*}"
case "${MIXER_MODE}" in
    software|hardware|none) ;;
    *) MIXER=software ;;
esac
validate_string "${MIXER}" "MIXER"
echo "$MIXER"
VALIDATION

assert_mixer() {
    local input="$1" expected="$2" desc="$3"
    actual=$(MIXER="$input" sh "$VALIDATOR" 2>/dev/null) || actual="REJECTED"

    if [[ "$actual" == "$expected" ]]; then
        echo "  PASS: $desc (${input} -> ${actual})"
        pass=$((pass + 1))
    else
        echo "  FAIL: $desc (${input} -> ${actual}, expected ${expected})"
        fail=$((fail + 1))
    fi
}

echo "Testing MIXER validation..."

# Valid modes (pass through unchanged)
assert_mixer "software"          "software"          "bare software"
assert_mixer "hardware"          "hardware"          "bare hardware"
assert_mixer "none"              "none"              "bare none"
assert_mixer "hardware:Digital"  "hardware:Digital"  "hardware with element"
assert_mixer "hardware:PCM"      "hardware:PCM"      "hardware with PCM element"

# Invalid modes (fallback to software)
assert_mixer "invalid"           "software"           "invalid mode falls back"
assert_mixer "script"            "software"           "script mode rejected"

# Empty MIXER uses default (software)
assert_mixer ""                  "software"           "empty falls back to default"

# Invalid mode with metacharacters (neutralized by mode fallback)
assert_mixer 'hardware;rm'       "software"          "semicolon in mode falls back"
assert_mixer 'bad$(cmd)'         "software"          "cmd subst in mode falls back"

# Valid mode prefix with metacharacters in element (caught by validate_string)
assert_mixer 'hardware:x;rm'     "REJECTED"          "semicolon in element rejected"
assert_mixer 'hardware:$(cmd)'   "REJECTED"          "cmd subst in element rejected"
assert_mixer 'hardware:x&bg'     "REJECTED"          "ampersand in element rejected"

echo ""
if [[ "$fail" -gt 0 ]]; then
    echo "FAILED: $fail tests failed, $pass passed"
    exit 1
fi
echo "All $pass tests passed!"
