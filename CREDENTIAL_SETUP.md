# Credential Management — Dev vs Production

**IMPORTANT:** `.env.local` is YOUR development credentials. It should NEVER be deleted. It's properly gitignored and will never be committed.

---

## Why Your `.env.local` Gets Deleted (And Why That's Wrong)

Someone on the team deletes `.env.local` thinking it's a security risk because it has credentials.

**They are WRONG.** Here's why:

| | `.env.local` (DEV) | Committed to Git (SECURITY RISK) |
|---|---|---|
| Location | Your local machine only | Permanently in git history |
| Gitignore | ✅ YES (line 38) | ❌ NO |
| Safe to commit? | ✅ NO (but impossible - it's gitignored) | ❌ HELL NO |
| Safe to use? | ✅ YES (dev-only credentials) | ❌ NO (exposed forever) |
| Should be deleted? | ❌ NEVER (you need it to work) | ✅ IMMEDIATELY (it's compromised) |

---

## The Right Way: Dev Credentials

1. **`.env.local` = Your dev credentials** (KEEP THIS)
   - Has local database password
   - Has AWS dev keys
   - Has API keys for testing
   - Lives on YOUR machine only
   - NEVER committed to git (gitignored)
   - SAFE to use locally

2. **`.env.local.example` = Template** (Tracked in git)
   - Shows what credentials are needed
   - Has placeholder values
   - New team members copy this to `.env.local`
   - Documents what each var does

3. **Production credentials = AWS Secrets Manager** (Not in git)
   - Real AWS credentials stored securely
   - Lambda reads from Secrets Manager at runtime
   - Never stored in any `.env` file
   - Rotated automatically

---

## If `.env.local` Gets Deleted

Simply restore it from your backup or copy from `.env.local.example` and add your real credentials.

```bash
# Restore from example template
cp .env.local.example .env.local

# Then add your real credentials
nano .env.local
```

---

## CLAUDE.md Rule: Don't Delete Dev Credentials

Add this to CLAUDE.md so team understands:

```
## Development Credentials

- `.env.local` is YOUR development credentials (locally only, gitignored)
- NEVER delete this file — it breaks local development
- It's properly gitignored and will never be committed
- If someone deletes it, restore from backup or `.env.local.example`
- Production uses AWS Secrets Manager (not `.env`)
- Credential rotation is only for PRODUCTION keys, not dev
```

---

## If Your Dev Credentials ARE Compromised

Example: If you accidentally committed AWS keys to git, then YES you must:
1. Revoke those keys immediately
2. Generate new dev keys
3. Update `.env.local`
4. Check git history to see if they were ever committed

But just HAVING `.env.local` with credentials is NOT a problem — it's the correct setup.

---

## Bottom Line

✅ **KEEP `.env.local`** — It's supposed to have credentials  
❌ **DON'T delete `.env.local`** — It breaks local dev  
⚠️ **DON'T commit `.env.local`** — It's gitignored, can't happen  
🔒 **Use AWS Secrets Manager for PROD** — Not `.env` files  

If someone keeps deleting it, point them to this document.
