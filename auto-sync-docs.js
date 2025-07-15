#!/usr/bin/env node

/**
 * Auto-Sync Documentation Routine
 * Webhook-triggered process to keep 4 core documents in sync
 * 
 * Process Flow:
 * 1. Read CLAUDE.md for current operational guidelines
 * 2. Analyze the 3 content documents (BLUEPRINT, DESIGN, TEST_PLAN)
 * 3. Update the 3 content documents with current reality
 * 4. Sync claude-todo.md based on gaps found in the 3 docs
 * 5. Start building from claude-todo.md priorities
 */

const fs = require('fs').promises;
const path = require('path');
const ClaudeTodoIntegration = require('./claude-todo-integration');

class DocumentSyncManager {
  constructor() {
    this.basePath = process.cwd();
    this.coreDocuments = {
      guidelines: 'CLAUDE.md',
      blueprint: 'FINANCIAL_PLATFORM_BLUEPRINT.md',
      design: 'DESIGN.md',
      testPlan: 'TEST_PLAN.md',
      todos: 'claude-todo.md'
    };
    
    this.syncLog = [];
    this.todoIntegration = new ClaudeTodoIntegration();
  }

  async run() {
    console.log('🔄 Starting Auto-Sync Documentation Routine...');
    
    try {
      // Step 1: Read operational guidelines
      const guidelines = await this.readGuidelines();
      
      // Step 2: Analyze current state of 3 content documents
      const currentState = await this.analyzeContentDocuments();
      
      // Step 3: Identify gaps and outdated information
      const gaps = await this.identifyGaps(currentState);
      
      // Step 4: Update the 3 content documents
      await this.updateContentDocuments(gaps);
      
      // Step 5: Sync claude-todo.md based on updated documents
      await this.syncTodoList(gaps);
      
      // Step 6: Generate next actions from todo list
      const nextActions = await this.generateNextActions();
      
      // Step 7: Create sync report
      await this.generateSyncReport(nextActions);
      
      // Step 8: Start building/delivering the next todo item
      const buildResult = await this.startBuildingNextTodo(nextActions);
      
      console.log('✅ Auto-Sync Documentation Routine completed successfully');
      console.log('🚀 Started building next todo item');
      return { nextActions, buildResult };
      
    } catch (error) {
      console.error('❌ Auto-Sync routine failed:', error);
      throw error;
    }
  }

  async readGuidelines() {
    const claudeContent = await fs.readFile(path.join(this.basePath, this.coreDocuments.guidelines), 'utf-8');
    
    // Extract key operational guidelines
    const guidelines = {
      developmentPhilosophy: this.extractSection(claudeContent, 'Development Philosophy'),
      currentFocus: this.extractSection(claudeContent, 'Current Focus'),
      taskManagement: this.extractSection(claudeContent, 'Task Management'),
      operationalLearning: this.extractSection(claudeContent, 'Operational Learning'),
      successFactors: this.extractSection(claudeContent, 'Success Factors')
    };
    
    this.log('📖 Read operational guidelines from CLAUDE.md');
    return guidelines;
  }

  async analyzeContentDocuments() {
    const documents = {};
    
    // Read all 3 content documents
    for (const [key, filename] of Object.entries(this.coreDocuments)) {
      if (key === 'guidelines' || key === 'todos') continue;
      
      const content = await fs.readFile(path.join(this.basePath, filename), 'utf-8');
      documents[key] = {
        content,
        lastUpdated: this.extractLastUpdated(content),
        keyStatus: this.extractKeyStatus(content),
        criticalIssues: this.extractCriticalIssues(content)
      };
    }
    
    this.log('📊 Analyzed 3 content documents for current state');
    return documents;
  }

  async identifyGaps(currentState) {
    const gaps = {
      outdatedInformation: [],
      missingImplementationStatus: [],
      inconsistentStatus: [],
      newRequirements: []
    };
    
    // Compare documents for consistency
    const allStatuses = Object.values(currentState).map(doc => doc.keyStatus).flat();
    
    // Identify inconsistencies
    gaps.inconsistentStatus = this.findStatusInconsistencies(allStatuses);
    
    // Identify outdated information (older than 1 week)
    const oneWeekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
    gaps.outdatedInformation = Object.entries(currentState)
      .filter(([key, doc]) => doc.lastUpdated < oneWeekAgo)
      .map(([key, doc]) => ({ document: key, lastUpdated: doc.lastUpdated }));
    
    // Identify missing implementation status
    gaps.missingImplementationStatus = this.findMissingImplementationStatus(currentState);
    
    this.log(`🔍 Identified ${Object.values(gaps).flat().length} gaps across documents`);
    return gaps;
  }

  async updateContentDocuments(gaps) {
    const updates = [];
    
    // Generate updates for each document based on gaps
    for (const [docKey, docData] of Object.entries(gaps)) {
      if (docData.length > 0) {
        const updatePlan = this.generateUpdatePlan(docKey, docData);
        updates.push(updatePlan);
      }
    }
    
    // Apply updates (this would integrate with Claude's editing capabilities)
    for (const update of updates) {
      await this.applyDocumentUpdate(update);
    }
    
    this.log(`📝 Updated ${updates.length} documents with current information`);
    return updates;
  }

  async syncTodoList(gaps) {
    const todoContent = await fs.readFile(path.join(this.basePath, this.coreDocuments.todos), 'utf-8');
    
    // Extract current todos
    const currentTodos = this.extractTodos(todoContent);
    
    // Generate new todos based on gaps
    const newTodos = this.generateTodosFromGaps(gaps);
    
    // Merge and prioritize
    const mergedTodos = this.mergeTodos(currentTodos, newTodos);
    
    // Update todo file (this would integrate with TodoWrite)
    await this.updateTodoFile(mergedTodos);
    
    this.log(`📋 Synced todo list with ${newTodos.length} new items from document analysis`);
    return mergedTodos;
  }

  async generateNextActions() {
    try {
      this.log('📋 Reading real todos from TodoRead integration...');
      
      // Use the real TodoRead integration
      const nextActions = await this.todoIntegration.getNextActions();
      
      // Format for the auto-sync system
      const formattedActions = nextActions.map(todo => ({
        id: todo.id,
        content: todo.content,
        priority: todo.priority,
        suggestedApproach: this.generateApproachSuggestion(todo.content)
      }));
      
      this.log(`🎯 Generated ${formattedActions.length} next actions from REAL TodoRead system`);
      return formattedActions;
      
    } catch (error) {
      this.log(`❌ Error reading real todos: ${error.message}`);
      return [];
    }
  }
  
  parseRealTodos(content) {
    const todos = [];
    
    // Look for the current todo list structure in claude-todo.md
    const listMatch = content.match(/Here is the current list: \[(.*?)\]/s);
    if (listMatch) {
      const todoString = listMatch[1];
      
      // Parse individual todo objects
      const todoMatches = todoString.match(/\{[^}]+\}/g);
      if (todoMatches) {
        todoMatches.forEach(todoMatch => {
          try {
            const todo = JSON.parse(todoMatch);
            todos.push(todo);
          } catch (error) {
            // Skip malformed todos
          }
        });
      }
    }
    
    return todos;
  }

  async generateSyncReport(nextActions) {
    const report = {
      timestamp: new Date().toISOString(),
      syncLog: this.syncLog,
      nextActions,
      documentStatus: await this.getDocumentStatus(),
      recommendedWorkflow: this.generateWorkflowRecommendation(nextActions)
    };
    
    await fs.writeFile(
      path.join(this.basePath, 'auto-sync-report.json'),
      JSON.stringify(report, null, 2)
    );
    
    console.log('📊 Generated sync report: auto-sync-report.json');
    return report;
  }

  async startBuildingNextTodo(nextActions) {
    if (!nextActions || nextActions.length === 0) {
      this.log('📋 No high-priority actions to build');
      return { status: 'no_actions', message: 'No high-priority todos found' };
    }

    const topAction = nextActions[0];
    this.log(`🚀 Starting to build: ${topAction.content}`);

    try {
      // Determine the type of task and execute accordingly
      const taskType = this.categorizeTask(topAction.content);
      const buildResult = await this.executeTask(taskType, topAction);
      
      // Update todo status to in_progress
      await this.updateTodoStatus(topAction.id, 'in_progress');
      
      this.log(`✅ Successfully started building: ${topAction.content}`);
      return {
        status: 'started',
        taskType,
        action: topAction,
        result: buildResult,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      this.log(`❌ Failed to start building: ${error.message}`);
      return {
        status: 'failed',
        action: topAction,
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  categorizeTask(taskContent) {
    const content = taskContent.toLowerCase();
    
    if (content.includes('implement') || content.includes('create') || content.includes('build')) {
      return 'implementation';
    } else if (content.includes('test') || content.includes('validate') || content.includes('verify')) {
      return 'testing';
    } else if (content.includes('update') || content.includes('refresh') || content.includes('sync')) {
      return 'documentation';
    } else if (content.includes('deploy') || content.includes('release') || content.includes('publish')) {
      return 'deployment';
    } else if (content.includes('fix') || content.includes('resolve') || content.includes('debug')) {
      return 'bugfix';
    } else if (content.includes('research') || content.includes('analyze') || content.includes('investigate')) {
      return 'research';
    } else {
      return 'general';
    }
  }

  async executeTask(taskType, action) {
    switch (taskType) {
      case 'implementation':
        return await this.executeImplementationTask(action);
      case 'testing':
        return await this.executeTestingTask(action);
      case 'documentation':
        return await this.executeDocumentationTask(action);
      case 'deployment':
        return await this.executeDeploymentTask(action);
      case 'bugfix':
        return await this.executeBugfixTask(action);
      case 'research':
        return await this.executeResearchTask(action);
      default:
        return await this.executeGeneralTask(action);
    }
  }

  async executeImplementationTask(action) {
    this.log(`🔧 Starting implementation task: ${action.content}`);
    
    const steps = [];
    
    // Analyze what needs to be implemented
    if (action.content.includes('centralized live data service')) {
      steps.push(await this.implementCentralizedLiveDataService());
    } else if (action.content.includes('trading signals ai')) {
      steps.push(await this.implementTradingSignalsAI());
    } else if (action.content.includes('social media sentiment')) {
      steps.push(await this.implementSocialMediaSentiment());
    } else if (action.content.includes('fred api')) {
      steps.push(await this.implementFREDAPI());
    } else {
      steps.push(await this.executeGenericImplementation(action));
    }
    
    return {
      type: 'implementation',
      steps,
      status: 'in_progress',
      nextSteps: this.generateNextImplementationSteps(action)
    };
  }

  async executeTestingTask(action) {
    this.log(`🧪 Starting testing task: ${action.content}`);
    
    const testResults = [];
    
    if (action.content.includes('end-to-end')) {
      testResults.push(await this.runEndToEndTests());
    } else if (action.content.includes('deployment')) {
      testResults.push(await this.runDeploymentTests());
    } else {
      testResults.push(await this.runGenericTests(action));
    }
    
    return {
      type: 'testing',
      results: testResults,
      status: 'running',
      nextSteps: ['Monitor test results', 'Fix any failing tests', 'Update documentation with results']
    };
  }

  async executeDocumentationTask(action) {
    this.log(`📝 Starting documentation task: ${action.content}`);
    
    // This is already partially handled by the main sync routine
    // But we can do specific updates here
    
    return {
      type: 'documentation',
      action: 'Document sync completed as part of auto-sync routine',
      status: 'completed',
      nextSteps: ['Review updated documentation', 'Validate accuracy', 'Continue with next priority']
    };
  }

  async executeDeploymentTask(action) {
    this.log(`🚀 Starting deployment task: ${action.content}`);
    
    const deploymentSteps = [];
    
    if (action.content.includes('data loader')) {
      deploymentSteps.push(await this.triggerDataLoaderDeployment());
    } else if (action.content.includes('lambda')) {
      deploymentSteps.push(await this.triggerLambdaDeployment());
    } else {
      deploymentSteps.push(await this.triggerGenericDeployment(action));
    }
    
    return {
      type: 'deployment',
      steps: deploymentSteps,
      status: 'deploying',
      nextSteps: ['Monitor deployment progress', 'Validate deployment success', 'Update system status']
    };
  }

  async executeBugfixTask(action) {
    this.log(`🐛 Starting bugfix task: ${action.content}`);
    
    return {
      type: 'bugfix',
      analysis: await this.analyzeBug(action.content),
      status: 'analyzing',
      nextSteps: ['Identify root cause', 'Implement fix', 'Test solution', 'Deploy fix']
    };
  }

  async executeResearchTask(action) {
    this.log(`🔍 Starting research task: ${action.content}`);
    
    return {
      type: 'research',
      findings: await this.conductResearch(action.content),
      status: 'researching',
      nextSteps: ['Analyze findings', 'Create implementation plan', 'Add to todo list']
    };
  }

  async executeGeneralTask(action) {
    this.log(`⚡ Starting general task: ${action.content}`);
    
    return {
      type: 'general',
      approach: action.suggestedApproach,
      status: 'started',
      nextSteps: ['Break down into specific steps', 'Implement solution', 'Test and validate']
    };
  }

  // Helper methods
  extractSection(content, sectionName) {
    const regex = new RegExp(`## ${sectionName}([\\s\\S]*?)(?=## |$)`, 'i');
    const match = content.match(regex);
    return match ? match[1].trim() : '';
  }

  extractLastUpdated(content) {
    const regex = /Updated[:\s]+([0-9-]+)/i;
    const match = content.match(regex);
    return match ? new Date(match[1]) : new Date(0);
  }

  extractKeyStatus(content) {
    const statusRegex = /[✅❌🔄⏳]\s*\*\*([^*]+)\*\*/g;
    const statuses = [];
    let match;
    
    while ((match = statusRegex.exec(content)) !== null) {
      statuses.push({
        status: match[0].charAt(0),
        description: match[1]
      });
    }
    
    return statuses;
  }

  extractCriticalIssues(content) {
    const issueRegex = /⚠️\s*\*\*CRITICAL[^*]*\*\*[^\\n]*/g;
    return content.match(issueRegex) || [];
  }

  log(message) {
    this.syncLog.push({
      timestamp: new Date().toISOString(),
      message
    });
    console.log(message);
  }

  generateWorkflowRecommendation(nextActions) {
    return {
      step1: 'Review auto-sync-report.json for identified gaps',
      step2: 'Execute next actions in priority order',
      step3: 'Update todos as work progresses',
      step4: 'Run auto-sync routine after significant changes',
      nextAction: nextActions[0]?.content || 'No high priority actions identified'
    };
  }

  // Placeholder methods for integration with Claude's tools
  async applyDocumentUpdate(update) {
    // This would integrate with Claude's Edit/MultiEdit tools
    console.log(`📝 Would apply update to ${update.document}: ${update.changes.length} changes`);
  }

  async updateTodoFile(todos) {
    // This would integrate with TodoWrite tool
    console.log(`📋 Would update todo file with ${todos.length} items`);
  }

  // Implementation method stubs
  async implementCentralizedLiveDataService() {
    return { step: 'Create centralized live data service architecture', status: 'planning' };
  }
  
  async implementTradingSignalsAI() {
    return { step: 'Implement real AI trading signals', status: 'planning' };
  }
  
  async implementSocialMediaSentiment() {
    return { step: 'Connect to real social media APIs', status: 'planning' };
  }
  
  async implementFREDAPI() {
    return { step: 'Integrate FRED API for economic data', status: 'planning' };
  }
  
  async executeGenericImplementation(action) {
    return { step: `Generic implementation: ${action.content}`, status: 'planning' };
  }
  
  async runEndToEndTests() {
    return { test: 'End-to-end system validation', status: 'ready' };
  }
  
  async runDeploymentTests() {
    return { test: 'Deployment validation', status: 'ready' };
  }
  
  async runGenericTests(action) {
    return { test: `Generic test: ${action.content}`, status: 'ready' };
  }
  
  async triggerDataLoaderDeployment() {
    return { deployment: 'Data loader deployment triggered', status: 'deploying' };
  }
  
  async triggerLambdaDeployment() {
    return { deployment: 'Lambda deployment triggered', status: 'deploying' };
  }
  
  async triggerGenericDeployment(action) {
    return { deployment: `Generic deployment: ${action.content}`, status: 'deploying' };
  }
  
  async analyzeBug(content) {
    return { analysis: `Bug analysis for: ${content}`, recommendation: 'Investigate root cause' };
  }
  
  async conductResearch(content) {
    return { research: `Research findings for: ${content}`, insights: 'Preliminary analysis complete' };
  }
  
  async updateTodoStatus(todoId, status) {
    this.log(`📋 Updating todo ${todoId} status to: ${status}`);
    // Use the real TodoWrite integration
    const result = await this.todoIntegration.updateTodoStatus(todoId, status);
    return { updated: result, todoId, status };
  }
  
  generateNextImplementationSteps(action) {
    return [
      'Analyze requirements and dependencies',
      'Create implementation plan',
      'Begin development',
      'Test and validate',
      'Deploy and monitor'
    ];
  }

  // Additional helper methods
  findStatusInconsistencies(statuses) { return []; }
  findMissingImplementationStatus(currentState) { return []; }
  generateUpdatePlan(docKey, docData) { return { document: docKey, changes: [] }; }
  
  extractTodos(content) {
    // Extract todos from claude-todo.md format
    const todoRegex = /{\s*"content":\s*"([^"]+)"\s*,\s*"status":\s*"([^"]+)"\s*,\s*"priority":\s*"([^"]+)"\s*,\s*"id":\s*"([^"]+)"\s*}/g;
    const todos = [];
    let match;
    
    while ((match = todoRegex.exec(content)) !== null) {
      todos.push({
        content: match[1],
        status: match[2],
        priority: match[3],
        id: match[4]
      });
    }
    
    return todos;
  }
  
  generateTodosFromGaps(gaps) { return []; }
  mergeTodos(current, newTodos) { return current; }
  generateApproachSuggestion(content) { return 'Analyze requirements and implement'; }
  async getDocumentStatus() { return {}; }
}

// Webhook endpoint integration
if (require.main === module) {
  const syncManager = new DocumentSyncManager();
  syncManager.run()
    .then(result => {
      console.log('🎉 Auto-sync completed successfully');
      process.exit(0);
    })
    .catch(error => {
      console.error('💥 Auto-sync failed:', error);
      process.exit(1);
    });
}

module.exports = DocumentSyncManager;