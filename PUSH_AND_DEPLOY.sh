#!/bin/bash
set -e

echo "════════════════════════════════════════════════════════════════════════════"
echo "  GitHub Push & AWS Deployment Monitor"
echo "════════════════════════════════════════════════════════════════════════════"
echo ""

# Check if we're in the right directory
if [ ! -f ".git/config" ]; then
    echo "❌ Error: Not in git repository root"
    exit 1
fi

echo "📊 Current Status:"
echo "───────────────────────────────────────────────────────────────────────────"
git log --oneline -1
echo ""
git status --short
echo ""

# Show what will be pushed
echo "📤 Commits ready to push:"
echo "───────────────────────────────────────────────────────────────────────────"
git log origin/main..HEAD --oneline
echo ""

# Show the specific changes
echo "🔧 Changes in the fix commit (ce50fa060):"
echo "───────────────────────────────────────────────────────────────────────────"
git show --stat ce50fa060
echo ""

# Try to push
echo "🚀 Attempting to push to GitHub..."
echo "───────────────────────────────────────────────────────────────────────────"

if git push origin main 2>&1; then
    echo ""
    echo "✅ SUCCESS! Changes pushed to GitHub"
    echo ""
    echo "GitHub Actions will now automatically:"
    echo "  1. Build the Lambda function"
    echo "  2. Deploy to AWS"
    echo "  3. Update API Gateway"
    echo "  4. Invalidate CloudFront cache"
    echo ""
    echo "Monitor deployment:"
    echo "  https://github.com/argie33/algo/actions"
    echo ""
    echo "Expected completion: 5-10 minutes"
else
    echo ""
    echo "⚠️  Push failed (likely network issue on WSL2)"
    echo ""
    echo "ALTERNATIVE SOLUTIONS:"
    echo "───────────────────────────────────────────────────────────────────────────"
    echo ""
    echo "Option 1: Push from Windows PowerShell"
    echo "  cd C:\\path\\to\\algo"
    echo "  git push origin main"
    echo ""
    echo "Option 2: Push from VS Code"
    echo "  1. Open VS Code with the algo folder"
    echo "  2. Click Source Control (Ctrl+Shift+G)"
    echo "  3. Click three dots → Push"
    echo ""
    echo "Option 3: Push from GitHub Desktop"
    echo "  1. Open GitHub Desktop"
    echo "  2. Select 'algo' repository"
    echo "  3. Click 'Push to origin'"
    echo ""
    echo "Option 4: Use SSH (if configured)"
    echo "  git remote set-url origin git@github.com:argie33/algo.git"
    echo "  git push origin main"
    echo ""
    echo "Option 5: AWS CloudShell (in AWS Console)"
    echo "  aws cloudshell start"
    echo "  git clone https://github.com/argie33/algo.git"
    echo "  cd algo"
    echo "  git push origin main"
    echo ""
    exit 1
fi

echo ""
echo "🔄 Next steps:"
echo "───────────────────────────────────────────────────────────────────────────"
echo ""
echo "1. Wait for GitHub Actions to complete (check the Actions page)"
echo ""
echo "2. After deployment succeeds, load data:"
echo "   bash /tmp/run_critical_loaders.sh"
echo ""
echo "3. Verify the API is working:"
echo "   curl https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health"
echo ""

