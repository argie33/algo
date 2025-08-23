/**
 * Global Visual Testing Teardown
 * 
 * Cleans up after visual regression testing and generates comparison reports.
 */

import fs from 'fs/promises';
import path from 'path';

export default async function globalTeardown() {
  console.log('🧹 Running visual regression testing cleanup...');
  
  try {
    // Generate visual regression report
    await generateVisualRegressionReport();
    
    // Clean up temporary files
    await cleanupTempFiles();
    
    console.log('✅ Visual regression teardown completed successfully');
    
  } catch (error) {
    console.error('❌ Visual regression teardown failed:', error);
    // Don't throw - allow tests to complete even if cleanup fails
  }
}

async function generateVisualRegressionReport() {
  console.log('📊 Generating visual regression report...');
  
  const testResultsDir = path.join(process.cwd(), 'test-results');
  const visualReportDir = path.join(testResultsDir, 'visual-report');
  const screenshotsDir = path.join(testResultsDir, 'visual-artifacts');
  
  try {
    // Check if screenshots directory exists
    const screenshotStats = await fs.stat(screenshotsDir).catch(() => null);
    if (!screenshotStats) {
      console.log('ℹ️ No visual artifacts found - skipping report generation');
      return;
    }
    
    // Read all screenshot files
    const screenshotFiles = await fs.readdir(screenshotsDir, { recursive: true });
    const screenshots = screenshotFiles.filter(file => file.endsWith('.png'));
    
    // Categorize screenshots
    const categories = {
      passed: screenshots.filter(f => !f.includes('-diff') && !f.includes('-expected') && !f.includes('-actual')),
      failed: screenshots.filter(f => f.includes('-diff')),
      expected: screenshots.filter(f => f.includes('-expected')),
      actual: screenshots.filter(f => f.includes('-actual'))
    };
    
    // Generate HTML report
    const reportHtml = generateReportHtml(categories);
    
    // Ensure report directory exists
    await fs.mkdir(visualReportDir, { recursive: true });
    
    // Write report file
    const reportPath = path.join(visualReportDir, 'visual-regression-summary.html');
    await fs.writeFile(reportPath, reportHtml, 'utf8');
    
    console.log(`📄 Visual regression report generated: ${reportPath}`);
    
    // Generate summary statistics
    const summaryStats = {
      timestamp: new Date().toISOString(),
      totalScreenshots: screenshots.length,
      passedTests: categories.passed.length,
      failedTests: categories.failed.length,
      expectedImages: categories.expected.length,
      actualImages: categories.actual.length,
      testCoverage: {
        pages: countUniquePages(categories.passed),
        viewports: countUniqueViewports(categories.passed),
        browsers: countUniqueBrowsers(categories.passed)
      }
    };
    
    const summaryPath = path.join(visualReportDir, 'visual-regression-summary.json');
    await fs.writeFile(summaryPath, JSON.stringify(summaryStats, null, 2), 'utf8');
    
    console.log(`📊 Visual regression statistics saved: ${summaryPath}`);
    
  } catch (error) {
    console.error('❌ Failed to generate visual regression report:', error);
  }
}

function generateReportHtml(categories) {
  return `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visual Regression Test Report</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            padding: 30px;
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
            margin-bottom: 30px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }
        .stat-card {
            background: #f8f9fa;
            border-left: 4px solid #3498db;
            padding: 20px;
            border-radius: 4px;
        }
        .stat-number {
            font-size: 2em;
            font-weight: bold;
            color: #2c3e50;
        }
        .stat-label {
            color: #7f8c8d;
            margin-top: 5px;
        }
        .section {
            margin-bottom: 40px;
        }
        .section h2 {
            color: #34495e;
            border-bottom: 1px solid #ecf0f1;
            padding-bottom: 10px;
        }
        .screenshot-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
        }
        .screenshot-item {
            border: 1px solid #ddd;
            border-radius: 8px;
            overflow: hidden;
            background: white;
        }
        .screenshot-item img {
            width: 100%;
            height: 200px;
            object-fit: cover;
            object-position: top;
        }
        .screenshot-info {
            padding: 15px;
        }
        .screenshot-name {
            font-weight: 600;
            margin-bottom: 5px;
            color: #2c3e50;
        }
        .screenshot-path {
            font-size: 0.9em;
            color: #7f8c8d;
            font-family: monospace;
        }
        .failed-tests {
            border-left-color: #e74c3c;
        }
        .failed-tests .stat-number {
            color: #e74c3c;
        }
        .passed-tests {
            border-left-color: #27ae60;
        }
        .passed-tests .stat-number {
            color: #27ae60;
        }
        .timestamp {
            text-align: center;
            color: #95a5a6;
            font-size: 0.9em;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎨 Visual Regression Test Report</h1>
        
        <div class="stats">
            <div class="stat-card passed-tests">
                <div class="stat-number">${categories.passed.length}</div>
                <div class="stat-label">Passed Screenshots</div>
            </div>
            <div class="stat-card failed-tests">
                <div class="stat-number">${categories.failed.length}</div>
                <div class="stat-label">Failed Comparisons</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">${categories.expected.length}</div>
                <div class="stat-label">Expected Images</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">${categories.actual.length}</div>
                <div class="stat-label">Actual Images</div>
            </div>
        </div>

        ${categories.failed.length > 0 ? `
        <div class="section">
            <h2>❌ Failed Visual Tests</h2>
            <div class="screenshot-grid">
                ${categories.failed.map(file => `
                    <div class="screenshot-item">
                        <img src="../visual-artifacts/${file}" alt="Failed test: ${file}" onerror="this.style.display='none'">
                        <div class="screenshot-info">
                            <div class="screenshot-name">Visual Diff</div>
                            <div class="screenshot-path">${file}</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
        ` : ''}

        <div class="section">
            <h2>✅ Successful Visual Tests</h2>
            <div class="screenshot-grid">
                ${categories.passed.slice(0, 12).map(file => `
                    <div class="screenshot-item">
                        <img src="../visual-artifacts/${file}" alt="Passed test: ${file}" onerror="this.style.display='none'">
                        <div class="screenshot-info">
                            <div class="screenshot-name">${formatScreenshotName(file)}</div>
                            <div class="screenshot-path">${file}</div>
                        </div>
                    </div>
                `).join('')}
                ${categories.passed.length > 12 ? `<div class="screenshot-item"><div class="screenshot-info"><div class="screenshot-name">... and ${categories.passed.length - 12} more screenshots</div></div></div>` : ''}
            </div>
        </div>

        <div class="timestamp">
            Report generated on ${new Date().toLocaleString()}
        </div>
    </div>

    <script>
        // Handle broken image links gracefully
        document.addEventListener('DOMContentLoaded', function() {
            const images = document.querySelectorAll('img');
            images.forEach(img => {
                img.addEventListener('error', function() {
                    this.parentElement.innerHTML = '<div style="padding: 20px; text-align: center; color: #999;">Screenshot not available</div>';
                });
            });
        });
    </script>
</body>
</html>`;
}

function formatScreenshotName(filename) {
  return filename
    .replace(/\.png$/, '')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase());
}

function countUniquePages(screenshots) {
  const pages = new Set();
  screenshots.forEach(file => {
    const match = file.match(/^([^-]+)/);
    if (match) pages.add(match[1]);
  });
  return pages.size;
}

function countUniqueViewports(screenshots) {
  const viewports = new Set();
  screenshots.forEach(file => {
    const match = file.match(/(desktop|tablet|mobile)/);
    if (match) viewports.add(match[1]);
  });
  return viewports.size;
}

function countUniqueBrowsers(screenshots) {
  const browsers = new Set();
  screenshots.forEach(file => {
    const match = file.match(/(chromium|firefox|webkit)/);
    if (match) browsers.add(match[1]);
  });
  return browsers.size;
}

async function cleanupTempFiles() {
  console.log('🗑️ Cleaning up temporary visual testing files...');
  
  try {
    // Clean up any temporary screenshot comparison files
    const tempDir = path.join(process.cwd(), 'temp-visual');
    try {
      await fs.rm(tempDir, { recursive: true, force: true });
      console.log('✅ Temporary files cleaned up');
    } catch (error) {
      // Directory doesn't exist, that's fine
      console.log('ℹ️ No temporary files to clean up');
    }
    
  } catch (error) {
    console.error('⚠️ Error during cleanup:', error);
  }
}