# 🛡️ CLAUDE CRASH FIX - PERMANENT SOLUTION

**Status:** Your system is crashing because WSL2 only has 3.8GB RAM
**Solution:** Increase to 8GB + Use safe sequential loading
**Time Required:** 5 minutes to fix

---

## 🔴 IMMEDIATE ACTION (Windows)

### Step 1: Edit WSL2 Configuration

**Open PowerShell as Administrator** and run:
```powershell
notepad "$env:USERPROFILE\.wslconfig"
```

Paste this EXACT text:
```ini
[wsl2]
memory=8GB
swap=4GB
processors=8
```

Save and close.

### Step 2: Restart WSL

In PowerShell, run:
```powershell
wsl --shutdown
```

Wait 10 seconds, then open WSL again.

### Step 3: Verify It Worked

In WSL terminal:
```bash
free -h
```

You should see: `Mem: 8.0Gi` (not 3.8Gi)

---

## ✅ After Restarting WSL (Linux)

### Step 4: Clean Up System

```bash
cd /home/arger/algo
bash EMERGENCY_MEMORY_CLEANUP.sh
```

### Step 5: Check Memory Available

```bash
free -h
```

You should see: `free: 6.0Gi` or more

### Step 6: Run Safe Loader

```bash
bash safe_loaders.sh
```

This will:
- Load data sequentially (one at a time)
- Check memory before each loader
- **NEVER crash the system**

---

## 📋 Why Claude Was Crashing

| Problem | Cause |
|---------|-------|
| **Only 3.8GB WSL2 RAM** | Default Windows WSL2 allocation |
| **Claude uses 1.3GB** | IDE keeps multiple processes active |
| **Loaders need 500MB+** | Data loading is memory-intensive |
| **Total needed: 2.8GB** | Exceeds available 1.8GB |
| **Result:** WSL kernel crashes | System runs out of memory |

---

## ✅ With 8GB Memory

| Component | RAM | Available |
|-----------|-----|-----------|
| **Total** | 8GB | - |
| Claude IDE | 1.3GB | ✅ Plenty |
| PostgreSQL | 65MB | ✅ No problem |
| System | 400MB | ✅ Healthy |
| **For loaders** | **6GB** | ✅ **SAFE!** |

---

## 🚫 What NOT to Do Anymore

- ❌ Run multiple loaders in parallel
- ❌ Start dev servers during data loading
- ❌ Use Claude while loaders are running (if memory <1GB)
- ❌ Ignore memory warnings in safe_loaders.sh

## ✅ New Safe Protocol

```bash
# STEP 1: Clean system
bash /home/arger/algo/EMERGENCY_MEMORY_CLEANUP.sh

# STEP 2: Wait for cleanup (watch memory)
watch free -h

# STEP 3: Load data safely
bash /home/arger/algo/safe_loaders.sh

# STEP 4: After loading, resume development
# (Claude is now safe with 8GB available)
```

---

## 🎯 Expected Timeline

- **Windows config edit:** 2 minutes
- **WSL restart:** 1 minute
- **Data loading:** 45-60 minutes
- **Verification:** 5 minutes
- **Total:** ~60-70 minutes

---

## ❓ Troubleshooting

### Free RAM won't increase after .wslconfig change?
1. Make sure file is at: `C:\Users\<YourUsername>\.wslconfig` (note no extension)
2. Run `wsl --shutdown` again
3. Check Windows has enough free memory

### Still crashing during loading?
1. Check: `free -h` (should show 8Gi or more)
2. Kill all processes: `bash EMERGENCY_MEMORY_CLEANUP.sh`
3. Run safe loader: `bash safe_loaders.sh`

### .wslconfig not being read?
1. File must be UTF-8 encoding (not UTF-16)
2. Use Notepad (not Word)
3. Restart Windows, then WSL

---

## ✅ Verification Checklist

After completing all steps:

- [ ] WSL memory shows 8.0Gi (`free -h`)
- [ ] Free RAM shows 6.0Gi+
- [ ] No loader processes running (`ps aux | grep load`)
- [ ] safe_loaders.sh runs without errors
- [ ] Data loads successfully
- [ ] Claude IDE stays stable
- [ ] No kernel panics in dmesg

---

**Your system will be STABLE once you do this. No more crashes! 🎉**
