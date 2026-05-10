import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

// Get lint output
const lintOutput = execSync('npm run lint 2>&1', { encoding: 'utf8' });

// Extract files with unescaped entities errors
const lines = lintOutput.split('\n');
const filesWithErrors = new Set();
let currentFile = '';

for (const line of lines) {
  if (line.startsWith('C:\\')) {
    currentFile = line;
    filesWithErrors.add(currentFile);
  }
}

console.log(`Found ${filesWithErrors.size} files with errors\n`);

// Fix each file
const replacements = [
  { pattern: /We're/g, replacement: 'We&apos;re' },
  { pattern: /doesn't/g, replacement: 'doesn&apos;t' },
  { pattern: /can't/g, replacement: 'can&apos;t' },
  { pattern: /it's/g, replacement: 'it&apos;s' },
  { pattern: /that's/g, replacement: 'that&apos;s' },
  { pattern: /won't/g, replacement: 'won&apos;t' },
  { pattern: /they're/g, replacement: 'they&apos;re' },
  { pattern: /let's/g, replacement: 'let&apos;s' },
  { pattern: /I'm/g, replacement: 'I&apos;m' },
  { pattern: /isn't/g, replacement: 'isn&apos;t' },
  { pattern: /you're/g, replacement: 'you&apos;re' },
  { pattern: /what's/g, replacement: 'what&apos;s' },
  { pattern: /—/g, replacement: '&mdash;' },  // em dash
  { pattern: /"/g, replacement: '&quot;' },   // double quote
];

let fixedCount = 0;

for (const file of filesWithErrors) {
  try {
    const fullPath = file.trim();
    if (!fs.existsSync(fullPath)) continue;

    let content = fs.readFileSync(fullPath, 'utf8');
    const originalContent = content;

    // Apply replacements only in JSX text (between > and </tag)
    // This is a simplified approach - just do careful string replacements
    for (const { pattern, replacement } of replacements) {
      content = content.replace(pattern, replacement);
    }

    if (content !== originalContent) {
      fs.writeFileSync(fullPath, content, 'utf8');
      fixedCount++;
      console.log(`✓ Fixed: ${path.basename(fullPath)}`);
    }
  } catch (err) {
    // Silently skip files that can't be processed
  }
}

console.log(`\nFixed ${fixedCount} files`);
console.log('Running lint again...\n');

try {
  execSync('npm run lint 2>&1', { encoding: 'utf8', stdio: 'inherit' });
} catch (err) {
  // Lint may exit with non-zero if there are still errors
}
