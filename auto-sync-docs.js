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
      
      console.log('✅ Auto-Sync Documentation Routine completed successfully');
      return nextActions;
      
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
    const todoContent = await fs.readFile(path.join(this.basePath, this.coreDocuments.todos), 'utf-8');
    const todos = this.extractTodos(todoContent);
    
    // Get high priority pending todos
    const nextActions = todos
      .filter(todo => todo.status === 'pending' && todo.priority === 'high')
      .slice(0, 3) // Top 3 high priority items
      .map(todo => ({
        id: todo.id,
        content: todo.content,
        priority: todo.priority,
        suggestedApproach: this.generateApproachSuggestion(todo.content)
      }));
    
    this.log(`🎯 Generated ${nextActions.length} next actions from todo list`);
    return nextActions;
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

  // Additional helper methods would be implemented here...
  findStatusInconsistencies(statuses) { return []; }
  findMissingImplementationStatus(currentState) { return []; }
  generateUpdatePlan(docKey, docData) { return { document: docKey, changes: [] }; }
  extractTodos(content) { return []; }
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