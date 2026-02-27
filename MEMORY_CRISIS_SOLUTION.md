# Memory Crisis Solution Guide

## The Problem: Why Your System Keeps Crashing 🔴

Your WSL2 has **only 3.8GB total RAM**, but competing processes need:

| Component | Memory |
|-----------|--------|
| Claude IDE (4 processes) | 1.3GB |
| PostgreSQL | 65MB |
| Operating System | ~400MB |
| **Available for loaders** | **~1.2GB** |

When you try to run multiple data loaders simultaneously (each ~90-100MB):
- 5 loaders × 100MB = 500MB
- This overwhelms the 1.2GB available
- **WSL kernel crashes** trying to allocate more

---

## Solution 1: Increase WSL2 Memory (PERMANENT FIX) ⭐

### On Windows:
1. Open PowerShell **as Administrator**
2. Create/edit: `C:\Users\<YourUsername>\.wslconfig`
3. Add these lines:
```ini
[wsl2]
memory=8GB
swap=4GB
processors=8
```
4. Save the file
5. Open PowerShell and run: `wsl --shutdown`
6. Wait 10 seconds
7. Open WSL again - you'll now have 8GB

### Verify:
```bash
free -h  # Should show 8Gi instead of 3.8Gi
```

---

## Solution 2: Use Safe Sequential Loading (IMMEDIATE) ✅

Instead of running multiple loaders at once, run them ONE AT A TIME:

```bash
cd /home/arger/algo
bash safe_loaders.sh
```

This script:
- Runs loaders sequentially (never parallel)
- Checks free memory before each (requires 300MB+)
- Prevents kernel crashes
- Takes longer but is stable

---

## Solution 3: Protocol for Safe Data Loading

**ALWAYS follow this when running loaders:**

```bash
# Step 1: Kill all dev servers
pkill -f "vite|webpack|npm"
pkill -f "node"

# Step 2: Kill any stuck loader processes
pkill -f "load.*\.py"

# Step 3: Check memory
free -h

# Step 4: Run safe sequential loader
cd /home/arger/algo
bash safe_loaders.sh

# Step 5: Monitor progress
tail -f /tmp/price_daily.log  # or other logs
```

---

## Solution 4: How to Protect Claude from Crashes

**DO NOT do these during data loading:**
- ❌ Open Claude IDE (Claude processes use 1.3GB)
- ❌ Run Vite dev server (`npm run dev`)
- ❌ Start API server (`node index.js`)
- ❌ Open multiple terminal tabs

**WAIT for data loading to complete**, then:
- ✅ Development work
- ✅ Testing
- ✅ Deploying

---

## Recommended Configuration (8GB WSL2)

### Before Data Loading:
```bash
# Check baseline memory
$ free -h
              total        used        free
Mem:           8.0Gi       2.0Gi       6.0Gi

# Kill dev servers
pkill -f "vite|npm|node"

# Check memory after cleanup
$ free -h
              total        used        free
Mem:           8.0Gi       1.2Gi       6.8Gi  ← Safe to load!

# Run loaders
bash safe_loaders.sh
```

### During Data Loading:
- Monitor: `watch free -h`
- Watch logs: `tail -f /tmp/price_daily.log`
- **Do NOT use Claude IDE**

### After Data Loading:
- Resume development work
- Deploy to AWS
- Restart services

---

## Current System State (Feb 26, 20:35 UTC)

| Item | Value |
|------|-------|
| WSL2 Total RAM | 3.8GB |
| Free RAM | 272MB |
| Needed for loaders | 300MB+ |
| Status | **READY for safe_loaders.sh** |

---

## Troubleshooting

### If loaders still crash:
1. **Check memory:** `free -h`
2. **Kill extra processes:** `ps aux | grep -E "python|node|vite"`
3. **Verify safe_loaders.sh is running:** `ps aux | grep safe`
4. **Check logs:** `/tmp/*.log`

### If memory won't increase:
1. Check .wslconfig is in correct location: `C:\Users\<YourUsername>\.wslconfig`
2. File format must be UTF-8 without BOM
3. Run `wsl --shutdown` to apply changes
4. Check Windows has enough available memory

---

## Next Steps

### IMMEDIATE (Today):
1. ✅ Edit `.wslconfig` with 8GB memory
2. ✅ Run `wsl --shutdown` to apply
3. ✅ Restart WSL
4. ✅ Verify: `free -h` (should show 8Gi)
5. ✅ Run: `bash /home/arger/algo/safe_loaders.sh`

### AFTER Loading Completes:
1. Push to GitHub
2. Deploy to AWS
3. Resume development work

---

**Key Rule:** *Never run data loaders and Claude IDE simultaneously. Sequential loading = stable system.*
