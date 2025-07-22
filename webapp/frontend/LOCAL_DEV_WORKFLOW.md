# 🚀 Local Development Workflow

Never push broken code again! This workflow catches F12 console errors, build failures, and test issues **before** you push.

## Quick Commands

```bash
# 🔄 Full validation before pushing (recommended)
npm run validate

# 🧪 Quick test cycle (fast feedback)
npm run test:unit -- --run --reporter=basic

# 🔍 Just check for console errors  
node scripts/console-error-check.js

# 🚀 Pre-push validation
npm run pre-push
```

## Development Cycle

### The "Find-Fix-Test" Loop

```bash
# 1. Make your changes
# 2. Test locally BEFORE pushing
npm run validate

# 3. If errors found, fix them
# 4. Test again
npm run validate

# 5. When clean, push
git add . && git commit -m "Your changes" && git push
```

### What Gets Checked

1. **Build Check** ✅
   - Vite build succeeds
   - No TypeScript/build errors
   - All imports resolve

2. **Console Error Check** 🔍
   - Launches real browser
   - Tests key pages (/, /dashboard, /portfolio, /trading)
   - Captures console.error, page errors, network errors
   - **Flags critical errors like `typography.pxToRem`**

3. **Unit Tests** 🧪
   - Fast unit test suite
   - Component tests
   - Service tests

4. **Integration Tests** 🔗
   - Sample integration tests
   - API connectivity
   - Core workflows

## Error Categories

### 🚨 CRITICAL (Must Fix)
- `typography.pxToRem is not a function`
- `Cannot read properties of undefined`
- `TypeError`, `ReferenceError`, `SyntaxError`
- `Uncaught Error`

### ⚠️ WARNING (Review)
- Network errors (400+)
- Console warnings
- Performance issues

## VS Code Integration

Use **Ctrl+Shift+P** → **Tasks: Run Task**:
- `🚀 Validate Before Push`
- `🔄 Dev Cycle: Build + Test + Validate`
- `🧪 Quick Test Cycle`
- `🔍 Console Error Check`

## Automated Git Hooks

```bash
# Optional: Set up git hooks
echo "npm run validate" > .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

## Troubleshooting

### "puppeteer not found"
```bash
npm install puppeteer --save-dev
```

### "Server won't start"
```bash
# Kill any hanging processes
npx kill-port 3002
npm run validate
```

### "Tests timing out"
```bash
# Run smaller test batches
npm run test:unit -- --run src/tests/unit/components/
```

## Example Output

```bash
🚀 Running Local Development Validation

🔄 Build Check...
✅ Build Check

🔄 Type Check...
✅ Type Check

🔄 Unit Tests...
✅ Unit Tests

🔍 Checking for console errors...
📄 Testing /...
  ✅ No errors
📄 Testing /dashboard...
  ❌ Found 1 errors
📄 Testing /portfolio...
  ✅ No errors

📊 Console Error Check Results

❌ FOUND ERRORS ON 1 PAGES:

📄 /dashboard:
  🚨 [CRITICAL] TypeError: e.typography.pxToRem is not a function
      at Chip.js:86:32

🚨 CRITICAL ERRORS FOUND - DO NOT PUSH!
These errors will break the app in production.
```

## Best Practices

1. **Run `npm run validate` before every push**
2. **Fix critical errors immediately**
3. **Test the specific pages you modified**
4. **Keep validation fast (< 2 minutes total)**
5. **Don't skip validation for "small changes"**

---

🎯 **Goal**: Zero F12 errors in production, faster development cycles, higher code quality.