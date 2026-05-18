#!/bin/bash
# NyayaNode — Git Hook Setup
# Run once after cloning: bash setup_hooks.sh

HOOK_PATH=".git/hooks/pre-push"

HOOK_CONTENT='#!/bin/bash
# NyayaNode pre-push QA gate
# Runs unit tests before every git push. Blocks push if tests fail.

echo ""
echo "🏛️  NyayaNode pre-push QA gate running..."
echo "   Running unit tests (schema contracts + budget math)..."
echo ""

# Resolve the repo root
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Pick the venv pytest — works on both Windows (Scripts/) and Linux (bin/)
if [ -f "$REPO_ROOT/.venv/Scripts/pytest" ]; then
    PYTEST="$REPO_ROOT/.venv/Scripts/pytest"
elif [ -f "$REPO_ROOT/.venv/bin/pytest" ]; then
    PYTEST="$REPO_ROOT/.venv/bin/pytest"
else
    echo "⚠️  No venv pytest found — falling back to system pytest"
    PYTEST="pytest"
fi

# Run unit tests using the venv pytest
if "$PYTEST" qa/unit/ -q --tb=line 2>&1; then
    echo ""
    echo "✅ QA gate passed. Pushing..."
    echo ""
    exit 0
else
    echo ""
    echo "╔══════════════════════════════════════════════════╗"
    echo "║  ❌ NyayaNode QA gate FAILED                    ║"
    echo "║                                                  ║"
    echo "║  Unit tests must pass before pushing to main.   ║"
    echo "║                                                  ║"
    echo "║  Fix the failing tests and try again:            ║"
    echo "║    .venv/Scripts/pytest qa/unit/ -v --tb=short  ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo ""
    exit 1
fi
'

echo "📌 Installing pre-push hook at $HOOK_PATH..."

if [ ! -d ".git" ]; then
    echo "❌ Error: Run this from the repo root (where .git/ lives)"
    exit 1
fi

echo "$HOOK_CONTENT" > "$HOOK_PATH"
chmod +x "$HOOK_PATH"

echo "✅ Pre-push hook installed."
echo "   Every 'git push' will now run: pytest qa/unit/ -q"
echo ""
echo "   To skip the hook for an emergency push:"
echo "     git push --no-verify"
echo ""
