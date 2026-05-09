import { execSync } from 'child_process';
import fs from 'fs';

// Run lint and capture output
const lintOutput = execSync('npm run lint', { cwd: process.cwd(), encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }).catch ? '' : '';

// Get lint output from running lint and parsing the errors
try {
  execSync('npm run lint', { cwd: process.cwd(), stdio: 'pipe' });
} catch (e) {
  const output = e.stdout?.toString() || e.stderr?.toString() || e.message;
  
  // Parse warnings and group by file
  const warnings = {};
  output.split('\n').forEach(line => {
    const match = line.match(/^(.+?)\s+\d+:\d+\s+warning\s+(.+?)\s+no-unused-vars/);
    if (match) {
      const [, file, msg] = match;
      if (!warnings[file]) warnings[file] = [];
      warnings[file].push(msg.split(' is ')[0].trim());
    }
  });
  
  console.log(`Found unused items in ${Object.keys(warnings).length} files:`);
  Object.entries(warnings).slice(0, 10).forEach(([file, items]) => {
    console.log(`\n${file}:`);
    items.slice(0, 5).forEach(item => console.log(`  - ${item}`));
    if (items.length > 5) console.log(`  ... and ${items.length - 5} more`);
  });
}
