#!/bin/bash

echo "╔════════════════════════════════════════════════════════════╗"
echo "║           FINAL VERIFICATION - GOAL COMPLETION TEST        ║"
echo "╚════════════════════════════════════════════════════════════╝"

cd /c/Users/arger/code/algo/webapp/frontend

echo ""
echo "Testing LOCAL environment..."
LOCAL_RESULT=$(node verify-local.mjs 2>&1 | grep -E "GOAL STATUS|Console errors" | head -2)
echo "$LOCAL_RESULT"

echo ""
echo "Testing AWS production..."
AWS_RESULT=$(node verify-aws.mjs 2>&1 | grep -E "GOAL STATUS|Console errors" | head -2)
echo "$AWS_RESULT"

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
if echo "$LOCAL_RESULT" | grep -q "0" && echo "$AWS_RESULT" | grep -q "0"; then
  echo "║          ✅ GOAL ACHIEVED - ALL ENVIRONMENTS CLEAN         ║"
else
  echo "║          ⏳ More work needed - review results above        ║"
fi
echo "╚════════════════════════════════════════════════════════════╝"
