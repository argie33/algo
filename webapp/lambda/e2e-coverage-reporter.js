/**
 * E2E Coverage Reporter
 * Generates comprehensive coverage reports for E2E tests
 */

class E2ECoverageReporter {
  constructor() {
    this.frontendCoverage = new Map();
    this.apiCoverage = new Map();
    this.journeyCoverage = new Map();
    this.databaseCoverage = new Map();
  }

  /**
   * Track frontend code coverage
   */
  trackFrontendCoverage(coverageData) {
    coverageData.forEach(file => {
      this.frontendCoverage.set(file.url, {
        totalLines: file.ranges.length,
        coveredLines: file.ranges.filter(r => r.count > 0).length,
        percentage: this.calculatePercentage(file.ranges)
      });
    });
  }

  /**
   * Track API endpoint coverage
   */
  trackApiCoverage(method, path, tested = true) {
    const key = `${method} ${path}`;
    this.apiCoverage.set(key, {
      tested,
      callCount: (this.apiCoverage.get(key)?.callCount || 0) + 1
    });
  }

  /**
   * Track user journey coverage
   */
  trackJourneyCoverage(journey, steps) {
    this.journeyCoverage.set(journey, {
      totalSteps: steps.length,
      completedSteps: steps.filter(s => s.completed).length,
      steps
    });
  }

  /**
   * Generate comprehensive coverage report
   */
  generateReport() {
    return {
      summary: {
        frontend: this.getFrontendSummary(),
        api: this.getApiSummary(),
        journeys: this.getJourneySummary(),
        overall: this.getOverallCoverage()
      },
      detailed: {
        frontend: Object.fromEntries(this.frontendCoverage),
        api: Object.fromEntries(this.apiCoverage),
        journeys: Object.fromEntries(this.journeyCoverage)
      },
      recommendations: this.getRecommendations()
    };
  }

  /**
   * Get frontend coverage summary
   */
  getFrontendSummary() {
    const files = Array.from(this.frontendCoverage.values());
    const totalLines = files.reduce((sum, file) => sum + file.totalLines, 0);
    const coveredLines = files.reduce((sum, file) => sum + file.coveredLines, 0);
    
    return {
      filesTotal: files.length,
      filesCovered: files.filter(f => f.coveredLines > 0).length,
      linesTotal: totalLines,
      linesCovered: coveredLines,
      percentage: totalLines > 0 ? (coveredLines / totalLines) * 100 : 0
    };
  }

  /**
   * Get API coverage summary
   */
  getApiSummary() {
    const endpoints = Array.from(this.apiCoverage.entries());
    const tested = endpoints.filter(([_, data]) => data.tested).length;
    
    return {
      endpointsTotal: endpoints.length,
      endpointsTested: tested,
      percentage: endpoints.length > 0 ? (tested / endpoints.length) * 100 : 0,
      untested: endpoints
        .filter(([_, data]) => !data.tested)
        .map(([endpoint]) => endpoint)
    };
  }

  /**
   * Get user journey coverage summary
   */
  getJourneySummary() {
    const journeys = Array.from(this.journeyCoverage.values());
    const totalSteps = journeys.reduce((sum, j) => sum + j.totalSteps, 0);
    const completedSteps = journeys.reduce((sum, j) => sum + j.completedSteps, 0);
    
    return {
      journeysTotal: journeys.length,
      journeysCompleted: journeys.filter(j => j.completedSteps === j.totalSteps).length,
      stepsTotal: totalSteps,
      stepsCompleted: completedSteps,
      percentage: totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0
    };
  }

  /**
   * Calculate overall E2E coverage score
   */
  getOverallCoverage() {
    const frontend = this.getFrontendSummary().percentage;
    const api = this.getApiSummary().percentage;
    const journeys = this.getJourneySummary().percentage;
    
    // Weighted average (journeys most important for E2E)
    const weightedScore = (journeys * 0.5) + (api * 0.3) + (frontend * 0.2);
    
    return {
      score: Math.round(weightedScore * 100) / 100,
      breakdown: { frontend, api, journeys },
      grade: this.getGrade(weightedScore)
    };
  }

  /**
   * Get recommendations for improving coverage
   */
  getRecommendations() {
    const recommendations = [];
    const summary = {
      frontend: this.getFrontendSummary(),
      api: this.getApiSummary(),
      journeys: this.getJourneySummary()
    };

    if (summary.journeys.percentage < 80) {
      recommendations.push({
        type: 'critical',
        area: 'User Journeys',
        message: `Only ${summary.journeys.percentage.toFixed(1)}% journey coverage. Focus on completing critical user workflows.`,
        priority: 1
      });
    }

    if (summary.api.percentage < 70) {
      recommendations.push({
        type: 'high',
        area: 'API Endpoints',
        message: `${summary.api.untested.length} API endpoints not tested. Add E2E tests for missing endpoints.`,
        priority: 2,
        details: summary.api.untested.slice(0, 5) // Top 5 untested
      });
    }

    if (summary.frontend.percentage < 60) {
      recommendations.push({
        type: 'medium',
        area: 'Frontend Code',
        message: `Frontend coverage at ${summary.frontend.percentage.toFixed(1)}%. Consider adding more comprehensive E2E interactions.`,
        priority: 3
      });
    }

    return recommendations.sort((a, b) => a.priority - b.priority);
  }

  /**
   * Get coverage grade
   */
  getGrade(percentage) {
    if (percentage >= 90) return 'A+';
    if (percentage >= 80) return 'A';
    if (percentage >= 70) return 'B';
    if (percentage >= 60) return 'C';
    if (percentage >= 50) return 'D';
    return 'F';
  }

  /**
   * Calculate percentage helper
   */
  calculatePercentage(ranges) {
    const covered = ranges.filter(r => r.count > 0).length;
    return ranges.length > 0 ? (covered / ranges.length) * 100 : 0;
  }

  /**
   * Export coverage data to file
   */
  exportToFile(filename = 'e2e-coverage-report.json') {
    const fs = require('fs');
    const report = this.generateReport();
    
    fs.writeFileSync(filename, JSON.stringify(report, null, 2));
    
    // Also generate human-readable HTML report
    this.generateHtmlReport(report, filename.replace('.json', '.html'));
    
    return report;
  }

  /**
   * Generate HTML coverage report
   */
  generateHtmlReport(report, filename) {
    const html = `
    <!DOCTYPE html>
    <html>
    <head>
      <title>E2E Coverage Report</title>
      <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .summary { background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 30px; }
        .metric { display: inline-block; margin: 10px 20px 10px 0; }
        .percentage { font-size: 24px; font-weight: bold; }
        .grade-A { color: #28a745; }
        .grade-B { color: #ffc107; }
        .grade-C { color: #fd7e14; }
        .grade-D, .grade-F { color: #dc3545; }
        .recommendations { margin-top: 30px; }
        .critical { border-left: 4px solid #dc3545; padding-left: 15px; }
        .high { border-left: 4px solid #fd7e14; padding-left: 15px; }
        .medium { border-left: 4px solid #ffc107; padding-left: 15px; }
        .untested { background: #f8f9fa; padding: 10px; margin: 10px 0; font-family: monospace; }
      </style>
    </head>
    <body>
      <h1>E2E Test Coverage Report</h1>
      <div class="summary">
        <h2>Overall Coverage: <span class="percentage grade-${report.summary.overall.grade}">${report.summary.overall.score}%</span> (${report.summary.overall.grade})</h2>
        
        <div class="metric">
          <h3>User Journeys</h3>
          <div class="percentage">${report.summary.journeys.percentage.toFixed(1)}%</div>
          <div>${report.summary.journeys.stepsCompleted}/${report.summary.journeys.stepsTotal} steps</div>
        </div>
        
        <div class="metric">
          <h3>API Endpoints</h3>
          <div class="percentage">${report.summary.api.percentage.toFixed(1)}%</div>
          <div>${report.summary.api.endpointsTested}/${report.summary.api.endpointsTotal} endpoints</div>
        </div>
        
        <div class="metric">
          <h3>Frontend Code</h3>
          <div class="percentage">${report.summary.frontend.percentage.toFixed(1)}%</div>
          <div>${report.summary.frontend.linesCovered}/${report.summary.frontend.linesTotal} lines</div>
        </div>
      </div>

      <div class="recommendations">
        <h2>Recommendations</h2>
        ${report.recommendations.map(rec => `
          <div class="${rec.type}">
            <h3>${rec.area}</h3>
            <p>${rec.message}</p>
            ${rec.details ? `<div class="untested">Untested: ${rec.details.join(', ')}</div>` : ''}
          </div>
        `).join('')}
      </div>

      <div style="margin-top: 40px; font-size: 12px; color: #666;">
        Generated: ${new Date().toISOString()}
      </div>
    </body>
    </html>
    `;

    const fs = require('fs');
    fs.writeFileSync(filename, html);
  }
}

module.exports = E2ECoverageReporter;

// Example usage:
if (require.main === module) {
  const reporter = new E2ECoverageReporter();
  
  // Example data
  reporter.trackJourneyCoverage('authentication', [
    { name: 'sign_up', completed: true },
    { name: 'sign_in', completed: true },
    { name: 'sign_out', completed: true },
    { name: 'password_reset', completed: false }
  ]);

  reporter.trackApiCoverage('GET', '/api/portfolio', true);
  reporter.trackApiCoverage('POST', '/api/orders', true);
  reporter.trackApiCoverage('DELETE', '/api/watchlist/:id', false);

  const report = reporter.exportToFile('sample-e2e-coverage.json');
  console.log('E2E Coverage:', report.summary.overall.score + '%', report.summary.overall.grade);
}