#!/bin/bash
# Run all CI checks locally before pushing
set -e

echo "🔍 Running all checks..."
echo ""

echo "📝 Checking code formatting..."
ruff format --check src/ tests/
echo "✓ Formatting OK"
echo ""

echo "🔎 Running linter..."
ruff check src/ tests/
echo "✓ Linting OK"
echo ""

echo "🧪 Running tests..."
pytest tests/ -q
echo "✓ Tests OK"
echo ""

echo "✅ All checks passed!"
