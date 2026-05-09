/**
 * Bundle Analysis - Identify what's making the bundle large
 */
import fs from 'fs';
import path from 'path';

function analyzeDirectory(dir, extensions = ['.js', '.jsx', '.ts', '.tsx']) {
  const results = {
    totalFiles: 0,
    totalSize: 0,
    largestFiles: [],
    byType: {},
    duplication: {},
  };

  function walk(currentPath) {
    const files = fs.readdirSync(currentPath);

    files.forEach((file) => {
      const fullPath = path.join(currentPath, file);
      const stat = fs.statSync(fullPath);

      if (stat.isDirectory() && !fullPath.includes('node_modules') && !fullPath.includes('dist')) {
        walk(fullPath);
      } else if (stat.isFile() && extensions.includes(path.extname(file))) {
        results.totalFiles++;
        results.totalSize += stat.size;

        // Track by type
        const ext = path.extname(file);
        if (!results.byType[ext]) results.byType[ext] = { count: 0, size: 0 };
        results.byType[ext].count++;
        results.byType[ext].size += stat.size;

        // Track largest files
        results.largestFiles.push({
          path: fullPath.replace(dir, ''),
          size: stat.size,
          sizeKB: (stat.size / 1024).toFixed(2),
        });
      }
    });
  }

  walk(dir);

  // Sort largest files
  results.largestFiles.sort((a, b) => b.size - a.size);
  results.largestFiles = results.largestFiles.slice(0, 30); // Top 30

  return results;
}

async function main() {
  const srcDir = './src';

  console.log('🔍 Analyzing bundle size...\n');

  const analysis = analyzeDirectory(srcDir);

  console.log('📊 Bundle Statistics\n');
  console.log(`Total Files: ${analysis.totalFiles}`);
  console.log(`Total Size: ${(analysis.totalSize / 1024 / 1024).toFixed(2)} MB`);
  console.log(`Average File Size: ${((analysis.totalSize / analysis.totalFiles) / 1024).toFixed(2)} KB\n`);

  console.log('📁 By File Type:\n');
  Object.entries(analysis.byType)
    .sort((a, b) => b[1].size - a[1].size)
    .forEach(([ext, data]) => {
      console.log(`  ${ext.padEnd(6)} - ${data.count} files, ${(data.size / 1024).toFixed(2)} KB`);
    });

  console.log('\n\n📈 Top 30 Largest Files:\n');
  analysis.largestFiles.forEach((file, i) => {
    const sizeStr = file.sizeKB;
    const warning = parseInt(sizeKB) > 50 ? ' ⚠️  TOO LARGE' : '';
    console.log(`${String(i + 1).padStart(2)}. ${sizeStr.padStart(8)} KB - ${file.path}${warning}`);
  });

  console.log('\n\n🎯 Optimization Recommendations:\n');

  const largeComponents = analysis.largestFiles.filter((f) => parseInt(f.sizeKB) > 50);
  if (largeComponents.length > 0) {
    console.log(`1. SPLIT LARGE COMPONENTS (${largeComponents.length} files > 50KB):`);
    largeComponents.slice(0, 5).forEach((f) => {
      console.log(`   - ${f.path} (${f.sizeKB} KB) → Consider splitting into smaller components`);
    });
  }

  console.log(`\n2. CODE SPLITTING OPPORTUNITIES:`);
  console.log(`   - Use React.lazy() for route-based code splitting`);
  console.log(`   - Lazy load heavy libraries (charts, editors, etc.)`);
  console.log(`   - Implement dynamic imports for large pages`);

  console.log(`\n3. DEPENDENCY CHECK:`);
  console.log(`   - Check for duplicate dependencies`);
  console.log(`   - Remove unused packages from package.json`);
  console.log(`   - Consider lighter alternatives`);

  // Save report
  fs.writeFileSync('bundle-analysis-report.json', JSON.stringify(analysis, null, 2));
  console.log(`\n📄 Full report saved to: bundle-analysis-report.json`);
}

main().catch(console.error);
