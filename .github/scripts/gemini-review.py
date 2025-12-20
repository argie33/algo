#!/usr/bin/env python3
"""
Gemini AI Code Review Script for GitHub Actions
Reviews PR changes and provides intelligent feedback
"""

import os
import subprocess
import google.generativeai as genai

def get_pr_changes():
    """Get the diff from the PR"""
    try:
        result = subprocess.run(
            ['git', 'diff', 'origin/main...HEAD'],
            capture_output=True,
            text=True
        )
        return result.stdout
    except Exception as e:
        print(f"Error getting git diff: {e}")
        return None

def review_with_gemini(diff_content):
    """Review code changes with Gemini"""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY not set")
        return None

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    prompt = f"""
You are an expert code reviewer. Analyze the following git diff and provide:

1. **Security Issues**: Any potential security vulnerabilities
2. **Performance Concerns**: Inefficiencies or bottlenecks
3. **Best Practices**: Code quality and maintainability issues
4. **Suggestions**: Specific improvements with code examples

Keep your review concise and actionable. Focus on critical issues.

Git Diff:
```
{diff_content[:50000]}  # Limit to 50K chars
```

Provide your review in markdown format.
"""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Error during review: {e}")
        return None

def main():
    print("🤖 Running Gemini AI Code Review...")

    # Get PR changes
    diff = get_pr_changes()
    if not diff:
        print("❌ No changes found")
        return

    # Review with Gemini
    review = review_with_gemini(diff)
    if not review:
        print("❌ Review failed")
        return

    # Save review output
    with open('review-output.md', 'w') as f:
        f.write("## 🤖 Gemini AI Code Review\n\n")
        f.write(review)

    print("✅ Review complete")
    print(review)

if __name__ == "__main__":
    main()
