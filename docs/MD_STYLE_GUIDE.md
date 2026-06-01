# .md File Style Guide

Goal: Token efficiency. Lean, actionable, scannable in <5 minutes.

## Rules

1. **No emoji or fancy Unicode** (✅, ❌, —, →, etc.)
   - Use plain text: YES/NO, plain hyphens, "to"
   - Exception: Code blocks (comments/examples are fine)

2. **Keep it short**
   - Procedural docs: 50-150 lines
   - Architecture docs: 100-200 lines
   - If >200 lines, extract sections to separate files

3. **Command-focused, not explanation-focused**
   - Lead with commands/configs
   - Brief reason why (1 line max)
   - Minimal setup instructions (belongs in tutorials, not docs)

4. **Remove:**
   - Verbose introductions ("This guide explains...")
   - Step-by-step setup instructions (use checklists or commands instead)
   - "Next steps" sections
   - "Support" or "Additional resources" sections
   - External links (except for critical APIs)
   - Checklists or planning docs
   - Nice-to-have examples

5. **Keep:**
   - System diagram/map (tables are fine)
   - Commands (bash, terraform, aws cli)
   - Essential configuration
   - Critical troubleshooting (errors users will see)
   - Link to code for details

## Structure

```markdown
# Title

One sentence: what this is.

## Section 1

Commands/config here.

## Section 2

More commands/config.

## Troubleshooting

| Problem | Cause | Fix |
| Issue | Root reason | Command/solution |
```

## Examples

GOOD (lean):
```markdown
# Alert Setup

Email alerts via SMTP.

## Local Testing

Set env vars, run test script, check email.

## AWS Deployment

Create secret in Secrets Manager, run terraform apply.

## Troubleshooting

| Email fails | Wrong credentials | Check SMTP settings |
```

BAD (bloated):
```markdown
# Alert System Setup & Testing Guide

This guide explains how to configure and test the complete alert 
system for the Algo trading platform in development and production 
environments. It covers step-by-step instructions...
[lots of verbose explanation]
# Next Steps
1. Configure...
2. Test...
[etc]
```

## When to Split

If a .md file grows >200 lines:
1. Keep overview in main file
2. Create sub-docs for each major section
3. Link to code for implementation details

Example:
- `docs/ALERTS_OVERVIEW.md` (50 lines)
- `docs/ALERTS_SETUP.md` (100 lines)
- `docs/ALERTS_CONFIG.md` (100 lines)
