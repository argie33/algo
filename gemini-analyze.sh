#!/bin/bash
# Gemini Code Analysis Helper Script
# Usage: ./gemini-analyze.sh [file or directory]

TARGET="${1:-.}"

if [ ! -e "$TARGET" ]; then
    echo "❌ Error: $TARGET does not exist"
    exit 1
fi

echo "🔍 Analyzing: $TARGET"

# Create analysis prompt based on target type
if [ -f "$TARGET" ]; then
    # Single file analysis
    CONTENT=$(cat "$TARGET")
    PROMPT="Analyze this code file for security issues, performance problems, and best practice violations. Provide specific suggestions:\n\n\`\`\`\n$CONTENT\n\`\`\`"
else
    # Directory analysis
    PROMPT="I need you to analyze the code structure in the '$TARGET' directory. Focus on:\n1. Architecture issues\n2. Security vulnerabilities\n3. Performance bottlenecks\n4. Code quality problems\n\nProvide actionable recommendations."
fi

# Run Gemini analysis
python3 /home/stocks/gemini-cli.py "$PROMPT"
