# Gemini AI Integration Setup

## ✅ Installed Components

- **Gemini CLI**: `/home/stocks/gemini-cli.py`
- **GitHub Actions**: `.github/workflows/gemini-code-review.yml`
- **Analysis Scripts**: `gemini-analyze.sh`, `.github/scripts/gemini-review.py`

## 🔑 API Key Configuration

Your API key is configured at: `~/.gemini_api_key`

**API Details:**
- **Key**: AIzaSyAg15be1Nee_vbdVBnukH4pAlF7FeJawgM
- **Project**: projects/185871229895
- **Model**: gemini-2.5-flash (fast and efficient)

## 📝 Usage

### 1. Command Line Interface

```bash
# Single question
gemini 'Explain Python decorators'

# Interactive mode
gemini --interactive

# Analyze a file
./gemini-analyze.sh path/to/file.py

# Analyze a directory
./gemini-analyze.sh webapp/lambda/routes/
```

### 2. GitHub Integration

#### A. Set up GitHub Secret
1. Go to your GitHub repository settings
2. Navigate to: Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Name: `GEMINI_API_KEY`
5. Value: `AIzaSyAg15be1Nee_vbdVBnukH4pAlF7FeJawgM`

#### B. Enable GitHub Actions
The workflow `.github/workflows/gemini-code-review.yml` will automatically:
- Run on every pull request
- Analyze code changes
- Post AI review comments

### 3. Local Code Analysis

```bash
# Quick file analysis
gemini "$(cat webapp/lambda/routes/scores.js | head -100) - Review this code for issues"

# Security audit
gemini 'Review webapp/lambda/middleware/auth.js for security vulnerabilities'

# Performance analysis
gemini 'Analyze loadquarterlyincomestatement.py for performance bottlenecks'
```

## 🛠️ Common Tasks

### Code Review
```bash
# Before committing
git diff | python3 -c "
import sys
diff = sys.stdin.read()
print('Review this diff:', diff[:5000])
" | xargs -I {} gemini '{}'
```

### Documentation Generation
```bash
gemini 'Generate comprehensive documentation for loadindustrydata.py'
```

### Bug Investigation
```bash
gemini 'Why is the sector data not showing on frontend? Here are the logs: [paste logs]'
```

### Architecture Analysis
```bash
./gemini-analyze.sh webapp/lambda/
```

## 🔒 Security Notes

- ✅ API key stored in `~/.gemini_api_key` (not in git)
- ✅ `.gemini_api_key` added to `.gitignore`
- ⚠️ Never commit API keys to repository
- ⚠️ For production, use GitHub Secrets or AWS Secrets Manager

## 📊 Available Models

Your API key has access to:
- `gemini-2.5-flash` (default - fast, efficient)
- `gemini-2.5-pro` (more capable, slower)
- `gemini-2.0-flash-thinking-exp` (advanced reasoning)
- Many more experimental models

To change model, edit `/home/stocks/gemini-cli.py` line 73.

## 🚀 Next Steps

1. ✅ CLI is working
2. ⏳ Add GitHub secret for automated reviews
3. ⏳ Test code analysis on actual files
4. ⏳ Integrate with CI/CD pipeline

## 🆘 Troubleshooting

**"GEMINI_API_KEY not found"**
```bash
# Check key file
cat ~/.gemini_api_key

# Re-create if needed
echo 'AIzaSyAg15be1Nee_vbdVBnukH4pAlF7FeJawgM' > ~/.gemini_api_key
chmod 600 ~/.gemini_api_key
```

**"Model not found"**
- Check available models: See GEMINI_SETUP.md
- Update model name in gemini-cli.py

**GitHub Actions not running**
- Add GEMINI_API_KEY to repository secrets
- Check Actions tab for error logs
