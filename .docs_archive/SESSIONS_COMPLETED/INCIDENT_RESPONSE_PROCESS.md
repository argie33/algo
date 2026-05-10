# Incident Response Process - Blameless Post-Mortem Culture

**Purpose:** Create a systematic, learning-focused process for handling production incidents. This is about continuous improvement, not blame.

**Philosophy:** Every incident is a gift — it reveals something broken in our system, process, or understanding. We investigate to learn, not to assign fault.

---

## Key Principle: Blameless Post-Mortem

> "If we can blame an individual for a problem, we are not investigating deeply enough." — John Allspaw

### Why Blameless?

❌ **Blame-Focused Culture:**
- People hide mistakes instead of reporting them
- Root causes go undiagnosed (superficial "human error" fix)
- Same problems happen again and again
- Team morale suffers

✅ **Blameless Culture:**
- Honest reporting leads to fast diagnosis
- Root cause investigation reveals systemic failures
- Fixes prevent recurrence (not just this incident)
- Team learns and improves together

---

## Incident Severity Levels

### 🔴 SEV-1: Critical (Immediate Response)

**Definition:** Trading is disabled or losing money.

**Examples:**
- Algo refuses to trade because data is completely missing
- Orders filled with extreme slippage (> 1%)
- Portfolio position count is wrong (off by >1 position)
- Money is disappearing from account (unexplained loss)

**Response Time:** < 5 minutes to acknowledge, < 30 minutes to diagnose

**Actions:**
1. Acknowledge the incident (Slack: "SEV-1 incident acknowledged")
2. Disable algo with feature flag: `python3 feature_flags.py --disable signal_tier_1_enabled`
3. Diagnose using runbooks: OPERATIONAL_RUNBOOKS.md
4. Implement fix or escalate
5. Verify recovery: `python3 audit_dashboard.py --loaders`
6. Schedule post-mortem (within 24 hours)

### 🟠 SEV-2: Significant (Urgent Response)

**Definition:** Algo is trading but with degraded quality.

**Examples:**
- Data is stale by 1-2 hours (but not missing)
- Slippage slightly elevated (0.5%)
- A few orders stuck for 10+ minutes
- API latency spikes to 5+ seconds
- Lambda timeout on one run (but next run succeeds)

**Response Time:** < 15 minutes to acknowledge, < 2 hours to diagnose

**Actions:**
1. Acknowledge in Slack
2. Gather context: Check logs, database state, recent changes
3. Implement mitigation (disable problematic feature, adjust parameters)
4. Monitor recovery
5. Schedule post-mortem (within 1 week)

### 🟡 SEV-3: Minor (Scheduled Response)

**Definition:** System degradation but no impact on trading.

**Examples:**
- Dashboard is slow to load
- Email alert didn't send
- Query takes longer than usual
- Non-critical log error

**Response Time:** Can wait until next business day

**Actions:**
1. Log the issue
2. Schedule investigation (within 1 week)
3. No emergency post-mortem needed (batch with others)

---

## Incident Timeline & Actions

### ⏰ T+0: Someone Discovers Problem

**What To Do:**
1. Check: "Is the algo still trading?" 
   - If YES → You have time, investigate methodically
   - If NO → SEV-1, activate emergency runbook

2. Describe what's happening:
   ```json
   {
     "discovered_at": "2026-05-09T14:30:00Z",
     "symptom": "price_daily table has zero rows loaded today",
     "impact": "algo SLA check fails, won't trade",
     "severity": "SEV-1",
     "what_I_see": "python3 audit_dashboard.py --loaders shows FAILED for price_daily"
   }
   ```

3. Post to Slack: `#incidents` channel (or create it if needed)
   ```
   🔴 SEV-1: Data load failure
   └ price_daily has zero rows
   └ Algo will not trade
   └ Investigating...
   ```

### ⏰ T+5min: Acknowledge & Activate Runbook

**What To Do:**
1. Follow OPERATIONAL_RUNBOOKS.md procedure for your symptom
2. Implement quick fix (usually a feature flag or manual trigger)
3. Verify fix worked: `python3 audit_dashboard.py --loaders`

**Update Slack:**
```
🔴→🟡 SEV-1 Acknowledged
└ Root cause: EventBridge scheduler failed (AWS service degradation)
└ Mitigation: Manually triggered ECS loader task
└ Status: Waiting for loader to complete (~5 min)
```

### ⏰ T+10-30min: Stabilize

**What To Do:**
1. System is operating normally again (or degraded but safe)
2. Confirm no data loss occurred
3. Log your actions for post-mortem

**Update Slack:**
```
🟡→🟢 RESOLVED: SEV-1 Data Load
└ Root cause: AWS EventBridge scheduler had transient DNS issue
└ Fix: Manual loader trigger (no code change needed)
└ Impact: 30 min delayed load, no trades during window (acceptable)
└ Post-mortem scheduled: 2026-05-09 4pm ET
```

### ⏰ T+24h: Post-Mortem Meeting

See "Post-Mortem Process" section below.

---

## Post-Mortem Process (Blameless Format)

### Step 1: Assemble the Timeline (30 minutes)

**Collect facts, not blame:**

```markdown
# Incident Timeline: Data Load Failure (May 9, 2026)

## 2026-05-09T14:30:00Z - Problem Discovered
- Operator checks audit dashboard
- Observes: price_daily has 0 rows loaded
- Action: Posts to #incidents

## 2026-05-09T14:32:00Z - Investigation Started
- Checked EventBridge logs: "DNS resolution timeout"
- Checked ECS task logs: "Never invoked"
- Checked RDS: "Connected and healthy"
- Conclusion: Scheduler failed to invoke loader

## 2026-05-09T14:33:00Z - Manual Mitigation
- Operator ran: aws ecs run-task ... (manual trigger)
- Loader invoked successfully
- Data loading started

## 2026-05-09T14:38:00Z - Recovery Complete
- 2,543 new rows loaded
- SLA check passes
- Algo resumes trading

## Root Cause (Single Point of Failure)
- EventBridge Scheduler sole dependency for data loading
- No fallback mechanism when scheduler fails
- AWS service degradation not immediately obvious
```

### Step 2: Identify Contributing Factors (15 minutes)

**Not "who caused it?" but "what let this happen?"**

```markdown
## Contributing Factors (Why Did This Happen?)

1. Single point of failure: EventBridge scheduler
   - No alternative trigger mechanism
   - No health check on scheduler status
   - No retry logic

2. Late problem discovery
   - Operator doesn't notice until 4pm ET (scheduled run is 4am ET)
   - 12+ hour gap between failure and discovery
   - Stale data was silently accepted for 12 hours

3. Unclear SLA impact
   - System design was clear: "fail-closed if data missing"
   - But operator assumption: "data is always fresh"
   - No alerting when data becomes stale

4. Scheduler failure reason unclear
   - AWS service issue (DNS timeout) not obvious in logs
   - Error message was buried in CloudWatch
   - Required detective work instead of clear alert
```

### Step 3: Identify Action Items (20 minutes)

**Fix systemic issues, not just this incident:**

```markdown
## Action Items (What We're Changing)

### Immediate (This Week)
- [ ] Add daily 5pm ET health check alert: "Data older than 24h?"
- [ ] Create CloudWatch alarm on EventBridge schedule failures
- [ ] Document manual loader trigger procedure in runbooks

### Short-term (Next 2 Weeks)
- [ ] Add secondary trigger mechanism: Lambda scheduled event (redundancy)
- [ ] Implement hourly freshness check (not just daily)
- [ ] Add Slack bot that posts data freshness every 2 hours

### Long-term (Engineering)
- [ ] Replace single scheduler with multi-scheduler architecture
- [ ] Implement data quality monitoring dashboard
- [ ] Add automated retry logic with exponential backoff
- [ ] Consider TimescaleDB continuous aggregates for freshness tracking

### Process Improvements
- [ ] Operator training: Check audit dashboard every morning at 9am ET
- [ ] On-call rotation: 1 person owns Monday-Friday 4am load window
- [ ] Quarterly incident review meeting (aggregate learnings)
```

### Step 4: Document Learnings (10 minutes)

**What did we learn about our system/process?**

```markdown
## Key Learnings

### About Our System
1. **Silence is Not Health** — No error doesn't mean things are fine
2. **Observability Gaps** — EventBridge failure wasn't visible until investigation
3. **Cascade Effects** — Single loader failure blocked entire algo

### About Our Process
1. **Humans Are Fallible** — Depending on manual checks is risky
2. **Redundancy Matters** — Need multiple paths to same outcome
3. **Clear Alerting Saves Time** — Buried logs cost 12 hours

### About Our Culture
1. **Blameless Investigation Works** — Team was honest, not defensive
2. **Procedures Help** — OPERATIONAL_RUNBOOKS.md worked perfectly
3. **Documentation Enabled Recovery** — Operator could fix without engineering help
```

### Step 5: Close the Loop

**Share findings, prevent future occurrences:**

```markdown
## Post-Mortem Summary

**Incident:** EventBridge scheduler failed, data load missed 12 hours
**Time to Detection:** 12 hours (should be <1 hour)
**Time to Recovery:** 8 minutes (excellent)
**Root Cause:** Single point of failure in scheduler architecture
**Impact:** Algo didn't trade for 30 min, no data loss

**Action Items (5 assigned, 2 future work, 1 training)**

**Next Steps:**
1. Health check alert deployed today
2. Secondary scheduler added by end of week
3. Team training scheduled for May 15
4. Architecture review scheduled for May 22
```

**Distribute to:**
- Team Slack: #incidents (summary + key learnings)
- Email: Team distribution list (full post-mortem doc)
- Backlog: Add action items to sprint backlog

---

## Running a Post-Mortem Meeting (Remote-Friendly Format)

### Participants (30 minutes total)

- **Incident Lead** (person who discovered + fixed)
- **Operations** (me, if this was production)
- **Engineering** (anyone who built affected system)
- **Data Lead** (if data issues)
- **Facilitator** (neutral person, runs the meeting)

### Meeting Format

1. **Opening (2 min):** 
   - "This is a blameless post-mortem. We're here to learn, not assign blame."
   - Read agenda: timeline → factors → actions → learnings

2. **Timeline Review (8 min):**
   - Incident lead walks through facts
   - Everyone adds missing details
   - "What else happened? Were there warning signs?"

3. **Contributing Factors (10 min):**
   - Facilitator asks: "Why did this happen?"
   - Dig deeper: "Why wasn't X in place?"
   - Root cause: "What systemic issue allowed this?"

4. **Action Items (7 min):**
   - "What will we change to prevent recurrence?"
   - Assign owners, set deadlines
   - Distinguish: immediate vs. short-term vs. long-term

5. **Closing (3 min):**
   - Summarize: 1-2 key learnings
   - Acknowledge good decisions made during incident
   - "Thank you for quick thinking and transparency"

### Meeting Tone

✅ **Good:**
- "EventBridge failed silently, which is easy to miss"
- "We didn't have monitoring for scheduler health"
- "The runbooks were clear and saved us time"

❌ **Avoid:**
- "Who set up the scheduler?" (blame)
- "Why didn't you check earlier?" (blame)
- "This was a dumb mistake" (shame)

---

## Incident Response Checklist (Use Every Time)

### During Incident
- [ ] Acknowledge in Slack (what, impact, severity)
- [ ] Use OPERATIONAL_RUNBOOKS.md for your symptom
- [ ] Implement quick mitigation (feature flag or manual trigger)
- [ ] Verify recovery: `python3 audit_dashboard.py --loaders`
- [ ] Log actions with timestamps for post-mortem

### After Incident (Within 24 Hours)
- [ ] Create post-mortem document (template above)
- [ ] Identify contributing factors (not blame)
- [ ] Assign action items with owners
- [ ] Schedule post-mortem meeting (if needed)
- [ ] Distribute findings to team

### Post-Mortem Meeting
- [ ] Invite relevant people (incident lead + engineers)
- [ ] Review timeline together
- [ ] Dig into contributing factors
- [ ] Agree on action items
- [ ] Close meeting with learnings

### After Meeting
- [ ] Update action items in backlog
- [ ] Track completion
- [ ] Celebrate completed items (they prevent future incidents)

---

## Scaling This Process

### For 1-2 Incidents Per Month
- Post-mortem meeting each time
- Team learns from each incident
- Action items prevent recurrence

### For 1-2 Incidents Per Week (Growing Pains)
- Daily sync: "What happened, what's the fix?"
- Weekly post-mortem meeting: Review all incidents together
- Pattern recognition: "These 3 incidents all involved X"
- Systematic fix: Add monitoring, redundancy, automation

### For Many Incidents (Warning Sign)
- This means: Your system is not resilient
- Or: You're discovering new issues (which is good!)
- Action: Don't blame the team, redesign the system
- Example: "We have 3 incidents about data freshness → add real-time monitoring"

---

## Example: A Real Post-Mortem (Annotated)

```markdown
# Post-Mortem: Lambda Timeout During Market Hours

## Incident Details
- **Date:** 2026-05-09, 2:45pm ET
- **Duration:** 12 minutes (7 missed signals)
- **Severity:** SEV-2 (Algo didn't trade during spike)

## Timeline

### 2:45pm ET - Lambda Invocation Begins
- EventBridge triggers algo orchestrator
- Phase 4 (signal quality scoring) begins

### 2:55pm ET - Lambda Timeout Occurs
- After 10 minutes, Lambda function timeout (15-min max)
- 245 candidate symbols being scored
- Process killed by Lambda runtime

### 2:56pm ET - Operator Notices
- CloudWatch shows timeout error
- Checks logs: "Process exited before completing request"

### 2:57pm ET - Quick Mitigation
- Operator disables Tier 5 (reduces candidate load)
- Feature flag: signal_tier_5_enabled = false
- Next invocation (2:58pm) succeeds in 4 minutes (fewer candidates)

### 3:15pm ET - Root Cause Identified
- Lambda memory: 1024 MB (1 GB)
- CPU time maxed during scoring
- 245 symbols × 25 checks each = expensive computation

### 3:20pm ET - Permanent Fix Deployed
- Lambda memory increased: 1024 → 2048 MB
- Cost increase: ~$0.05/run
- Next run completes in 8 minutes (more CPU available)

### 3:25pm ET - Recovery
- Re-enable Tier 5
- Algo resumes normal operation

## Root Cause Analysis (5 Whys)

1. Lambda timed out
2. Why? CPU couldn't complete scoring in 900 seconds
3. Why? 245 candidates × 25 checks = high compute load
4. Why? Lambda had only 1 CPU (1024 MB memory = 1/8 vCPU)
5. Why? We never stress-tested with this many candidates

## Contributing Factors

- **Engineering**: No load testing of signal pipeline
- **Operations**: Memory too low for production workload
- **Monitoring**: No alert on Lambda execution time trending
- **Process**: No capacity planning for market volume changes

## Action Items

| Item | Owner | Deadline | Status |
|------|-------|----------|--------|
| Increase Lambda memory to 2048 MB | DevOps | Today | ✓ DONE |
| Add CloudWatch alarm: Lambda duration >600s | DevOps | Today | ✓ DONE |
| Load test with 500+ candidates | Engineering | May 15 | In Progress |
| Document Lambda sizing guidance | Docs | May 10 | Pending |
| Quarterly capacity review process | DevOps | May 22 | Pending |

## Key Learnings

1. **Silent Failures Are Bad**
   - Lambda timeout didn't show in logs until investigation
   - Need proactive monitoring on duration trends

2. **Memory = CPU (on Lambda)**
   - We learned: 1024 MB is too tight
   - For this workload: 2048+ MB needed

3. **Runbooks Help**
   - Operator used OPERATIONAL_RUNBOOKS.md
   - Found quick fix (disable tier) in <2 minutes
   - Prevented extended outage

4. **Feature Flags Enabled Fast Recovery**
   - Could disable problematic feature without redeploy
   - Reduced incident from hours to minutes

## Outcome

- Fixed: Lambda memory, monitoring, load testing plan
- Prevented: Future timeouts during market volume spikes
- Improved: Incident response capability (team handled well)
```

---

## Summary: The Blameless Approach

**Before:** Incidents → Blame → Defensiveness → Lessons Missed

**After:** Incidents → Investigation → Systemic Fix → Continuous Improvement

**Result:** Team trusts the process, reports honestly, learns together, system gets better.

---

## Further Reading

- John Allspaw's "Blameless PostMortems" (industry standard)
- Google SRE Book: "Postmortem Culture"
- Etsy's Post-Mortem Format (this doc is loosely based on theirs)

---

**Remember:** Every incident is an opportunity. Make the most of it.
