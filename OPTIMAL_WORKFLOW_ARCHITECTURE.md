# Optimal Workflow Architecture: From First Principles

**Purpose:** Figure out what the BEST architecture is, not defend what we have

---

## STEP 1: Understand the Dependencies

### What We're Deploying
```
bootstrap-oidc
  ↓ (creates GitHub OIDC provider)
  ↓
template-core.yml (VPC)
  ├─ Creates: VPC, subnets, endpoints, security groups
  └─ Exports: StocksCore-VpcId, StocksCore-*Subnet*Id, etc.
  ↓ (needed by everything else)
  
template-app-stocks.yml (RDS + ECS cluster + Secrets)
  ├─ Imports: StocksCore-VpcId, subnets
  ├─ Creates: RDS, ECS cluster, Secrets Manager
  └─ Exports: StocksApp-SecretArn, StocksApp-ClusterArn, etc.
  ↓ (needed by three things)
  
├─ template-app-ecs-tasks.yml (39 loader tasks)
│   ├─ Imports: StocksApp-SecretArn, StocksApp-ClusterArn
│   └─ Creates: ECS task definitions
│
├─ template-webapp-lambda.yml (Frontend API)
│   ├─ Imports: StocksApp-SecretArn (indirectly, via workflow)
│   └─ Creates: Lambda, API Gateway, Cognito
│
└─ template-algo-orchestrator.yml (Algo engine)
    ├─ Imports: StocksApp-SecretArn (indirectly, via workflow)
    └─ Creates: Lambda, EventBridge, SNS
```

### The Dependency Chain
```
OIDC
  ↓
VPC (core-core infrastructure, rare)
  ↓
RDS + ECS (app infrastructure, occasional)
  ↓
├─ Loaders (frequent, ECS tasks)
├─ Webapp (frequent, Lambda)
└─ Algo (frequent, Lambda)
```

---

## STEP 2: What Makes Good Architecture?

### Principle 1: Separation of Concerns
- Different things should be separate
- Question: What defines "different"?
  - **Different change frequency?** (VPC vs RDS vs loaders)
  - **Different responsibility?** (infrastructure vs applications)
  - **Different risk level?** (risky RDS vs safe loaders)
  - **Different deployment timing?** (one-time vs ongoing)

### Principle 2: Dependency Clarity
- If A depends on B, it must be clear
- Two ways to express dependency:
  - **Implicit:** CloudFormation ImportValue (enforced by AWS)
  - **Explicit:** Workflow ordering (enforced by GitHub Actions)

### Principle 3: Deployment Safety
- Risky changes should require approval
- Safe changes can be automated
- Question: What's risky?
  - ❌ VPC changes (affects everything)
  - ❌ RDS changes (database = critical)
  - ✅ Loader code changes (isolated)
  - ✅ Webapp code changes (isolated)
  - ✅ Algo code changes (isolated)

### Principle 4: Operational Clarity
- Operations engineers should understand the flow
- Should be able to answer:
  - "What do I deploy first?"
  - "If X fails, does Y still deploy?"
  - "Can I update X without deploying Y?"

---

## STEP 3: Explore All Possible Architectures

### Architecture A: Monolithic (One workflow, everything together)

```
deploy-all.yml
  → template-core.yml
  → template-app-stocks.yml
  → template-app-ecs-tasks.yml
  → template-webapp-lambda.yml
  → template-algo-orchestrator.yml
```

**Pros:**
- Simple (one file)
- Guaranteed order

**Cons:**
- ❌ If loader code changes, VPC redeploys (wasteful)
- ❌ If VPC changes, everything redeploys (risky)
- ❌ Can't update one layer without others
- ❌ Long, slow deployments
- ❌ Violates "separation of concerns"

**Verdict:** ❌ Worst option

---

### Architecture B: Layered (5 separate workflows)

```
deploy-bootstrap.yml (manual)
deploy-core.yml (manual)
deploy-app-infrastructure.yml (auto)
deploy-app-stocks.yml (auto)
deploy-webapp.yml (auto)
deploy-algo-orchestrator.yml (auto)
```

**Current State:** This is what we have now

**Pros:**
- ✅ Clear separation
- ✅ Each layer can deploy independently
- ✅ Matches the dependency structure

**Cons:**
- ⚠️ 6 files to understand and maintain
- ⚠️ Implicit dependencies (must know that app-stocks must deploy before loaders)
- ⚠️ Easy to make mistakes (deploy loaders before app-stocks)

**Verdict:** ✅ Good, but requires discipline

---

### Architecture C: Consolidated (3 workflows)

```
deploy-bootstrap.yml (manual)
deploy-infrastructure.yml (manual)
  → template-core.yml
  → template-app-stocks.yml
  (Both infrastructure, both rare)
  
deploy-applications.yml (auto)
  → template-app-ecs-tasks.yml
  → template-webapp-lambda.yml
  → template-algo-orchestrator.yml
  (All applications, all frequent)
```

**Pros:**
- ✅ Clearer grouping (infrastructure vs applications)
- ✅ Fewer files (3 instead of 6)
- ✅ Natural separation (rare changes vs frequent)

**Cons:**
- ⚠️ "Infrastructure" includes two different layers (VPC vs RDS)
- ⚠️ Would deploy RDS even if only VPC changes
- ⚠️ Hard to update RDS alone

**Verdict:** ⚠️ Okay, but VPC and RDS are different concerns

---

### Architecture D: Risk-Based (3 workflows)

```
deploy-bootstrap.yml (manual, once)
deploy-safe-infrastructure.yml (auto)
  → template-core.yml
  → template-app-stocks.yml
  (Safe enough to auto-deploy)
  
deploy-applications.yml (auto)
  → template-app-ecs-tasks.yml
  → template-webapp-lambda.yml
  → template-algo-orchestrator.yml
```

**Same as Architecture C** — just different naming philosophy

**Verdict:** ⚠️ Works, but is VPC really safe to auto-deploy?

---

### Architecture E: Frequency-Based (4 workflows)

```
deploy-bootstrap.yml (manual, once)
deploy-core.yml (manual, rare)
  → template-core.yml

deploy-infrastructure.yml (manual, occasional)
  → template-app-stocks.yml

deploy-applications.yml (auto, frequent)
  → template-app-ecs-tasks.yml
  → template-webapp-lambda.yml
  → template-algo-orchestrator.yml
```

**Pros:**
- ✅ Groups by change frequency
- ✅ Risky things are manual
- ✅ Safe things are auto
- ✅ Clear operational model

**Cons:**
- ⚠️ 4 files (not huge)
- ⚠️ Requires understanding that bootstrap → core → infra → apps

**Verdict:** ✅ Good model

---

### Architecture F: Smart Monolithic (One workflow, smart ordering)

```
deploy-all.yml with conditional logic
  if: core.yml changed → deploy core (manual trigger)
  if: app-stocks.yml changed → deploy app-stocks (manual trigger)
  if: loader code changed → deploy loaders (auto)
  if: webapp code changed → deploy webapp (auto)
  if: algo code changed → deploy algo (auto)
  
  (Always: core → app-stocks → then apps in parallel)
```

**Pros:**
- ✅ One file to understand
- ✅ Guaranteed correct ordering
- ✅ Conditional triggers

**Cons:**
- ❌ Workflow becomes very complex
- ❌ Hard to debug "why didn't this deploy?"
- ❌ Not clear what changed
- ❌ Violates "simple is better"

**Verdict:** ❌ Too clever, hard to maintain

---

## STEP 4: What Does "Best" Mean?

**Best architecture balances:**

1. **Clarity** — Can an engineer understand it quickly?
2. **Safety** — Does it prevent dangerous mistakes?
3. **Efficiency** — Does it avoid wasted deployments?
4. **Maintainability** — Is it easy to update and debug?
5. **Flexibility** — Can you deploy one thing without others?

### Scoring Each Architecture

| Architecture | Clarity | Safety | Efficiency | Maintainability | Flexibility |
|-------------|---------|--------|-----------|-----------------|-------------|
| A (Monolithic) | ✅ | ❌ | ❌ | ✅ | ❌ |
| B (5 Separate) | ⚠️ | ⚠️ | ✅ | ⚠️ | ✅ |
| C (3 Consolidated) | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ |
| D (Risk-Based) | ✅ | ✅ | ⚠️ | ✅ | ⚠️ |
| E (Frequency-Based) | ✅ | ✅ | ✅ | ✅ | ✅ |
| F (Smart Monolithic) | ❌ | ✅ | ✅ | ❌ | ✅ |

---

## STEP 5: The Verdict — What Is "Best"?

### Winner: Architecture E (Frequency-Based, 4 Workflows)

```
deploy-bootstrap.yml
  Trigger: Manual (workflow_dispatch)
  Deploys: GitHub OIDC
  Frequency: Once at start
  Risk: N/A (one-time)

deploy-core.yml
  Trigger: Manual (workflow_dispatch)
  Deploys: VPC, endpoints, networking
  Frequency: Rare (infrastructure change)
  Risk: High (affects everything)

deploy-infrastructure.yml
  Trigger: Manual (workflow_dispatch)
  Deploys: RDS, ECS cluster, Secrets
  Frequency: Occasional (schema/config change)
  Risk: Medium (affects apps)

deploy-applications.yml
  Trigger: Auto (on code changes)
  Deploys: Loaders, Webapp, Algo (in parallel)
  Frequency: Frequent (code changes)
  Risk: Low (isolated to each app)
```

### Why This Is Best

1. **Clear trigger model:**
   - Manual for infrastructure (safe)
   - Auto for applications (efficient)

2. **Natural grouping:**
   - Bootstrap: One-time setup
   - Core: Foundational (VPC, endpoints)
   - Infrastructure: Shared (RDS, ECS)
   - Applications: Isolated (loaders, webapp, algo)

3. **Prevents mistakes:**
   - Can't deploy apps before infrastructure
   - Can't accidentally redeploy VPC on code change

4. **Operational clarity:**
   - Engineer knows: "Manual = infrastructure, Auto = applications"
   - Ordering is obvious: bootstrap → core → infra → apps

5. **Flexibility:**
   - Can deploy core alone (if needed)
   - Can deploy infra alone (if needed)
   - Can deploy each app independently

6. **Scalability:**
   - Adding new applications: just add to deploy-applications.yml
   - Adding new infrastructure: add new manual workflow
   - Simple pattern to follow

---

## CURRENT vs OPTIMAL

### We Have (6 Workflows)
```
deploy-bootstrap.yml ✅
deploy-core.yml ✅
deploy-app-infrastructure.yml ✅
deploy-app-stocks.yml (should be merged with others)
deploy-webapp.yml (should be in applications group)
deploy-algo-orchestrator.yml (should be in applications group)
```

### Should Have (4 Workflows)
```
deploy-bootstrap.yml
  ↓
deploy-core.yml
  ↓
deploy-infrastructure.yml
  ↓
deploy-applications.yml
  ├─ Loaders (template-app-ecs-tasks.yml)
  ├─ Webapp (template-webapp-lambda.yml)
  └─ Algo (template-algo-orchestrator.yml)
```

---

## How to Get There

### Option 1: Keep Current Structure + Document It
- Keep 6 separate workflows (what we have)
- Just document the ordering and dependencies
- **Cost:** More files, less clear
- **Benefit:** Easier individual updates

### Option 2: Consolidate to Optimal (4 Workflows)
- Merge deploy-app-stocks, deploy-webapp, deploy-algo into one deploy-applications.yml
- Rename deploy-app-infrastructure to deploy-infrastructure
- **Cost:** Some refactoring
- **Benefit:** Clearer architecture, easier to understand

### Option 3: Smart Middle Ground
- Keep deploy-app-infrastructure separate (occasional RDS changes)
- Merge loaders + webapp + algo into deploy-applications.yml
- Keep everything else separate
- **Result:** 5 workflows (good balance)

---

## My Recommendation

**Go with Option 2 (Consolidate to 4 Workflows).**

Why:
1. ✅ Clearest mental model (bootstrap → core → infra → apps)
2. ✅ Reduces files to maintain (4 vs 6)
3. ✅ Natural grouping matches actual usage
4. ✅ Easy to explain to new engineers
5. ✅ Scales well for future additions

### Changes Needed

1. **Merge deploy-app-stocks.yml + deploy-webapp.yml + deploy-algo-orchestrator.yml**
   - Into: deploy-applications.yml
   - Trigger: Auto on any app code change

2. **Rename deploy-app-infrastructure.yml**
   - To: deploy-infrastructure.yml
   - Trigger: Manual (occasional RDS changes)

3. **Keep bootstrap and core separate**
   - Both manual (infrastructure decisions)
   - Clear ordering

---

## Summary: What Is Best Architecture?

**Best = Matches operational reality:**
- Infrastructure decisions are rare and risky → Manual workflows
- Application updates are frequent and safe → Auto workflows
- Clear naming and grouping → Easy to understand and maintain

**Current structure has it partially right, but could be clearer with consolidation.**
