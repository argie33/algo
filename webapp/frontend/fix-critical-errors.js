#!/usr/bin/env node
/**
 * Fix critical syntax errors and undefined variables in React frontend
 */

const fs = require('fs');
const path = require('path');

console.log('🔧 Fixing critical frontend lint errors...');

// Fix escaped quotes issues
console.log('1. Fixing escaped quotes in auth components...');
const authFiles = [
  'src/components/auth/ConfirmationForm.jsx',
  'src/components/auth/ForgotPasswordForm.jsx',
  'src/components/auth/LoginForm.jsx',
  'src/components/auth/SessionWarningDialog.jsx',
  'src/components/onboarding/OnboardingWizard.jsx'
];

authFiles.forEach(file => {
  try {
    if (fs.existsSync(file)) {
      let content = fs.readFileSync(file, 'utf8');
      
      // Fix single quotes in JSX text
      content = content.replace(/Don't/g, "Don&apos;t");
      content = content.replace(/can't/g, "can&apos;t");
      content = content.replace(/won't/g, "won&apos;t");
      content = content.replace(/hasn't/g, "hasn&apos;t");
      content = content.replace(/doesn't/g, "doesn&apos;t");
      content = content.replace(/isn't/g, "isn&apos;t");
      content = content.replace(/we'll/g, "we&apos;ll");
      content = content.replace(/you'll/g, "you&apos;ll");
      content = content.replace(/it's/g, "it&apos;s");
      content = content.replace(/here's/g, "here&apos;s");
      content = content.replace(/that's/g, "that&apos;s");
      
      // Fix double quotes in JSX text
      content = content.replace(/"([^"]*)"(?=[\s\.<])/g, "&quot;$1&quot;");
      
      fs.writeFileSync(file, content);
      console.log(`   ✅ Fixed quotes in ${file}`);
    }
  } catch (e) {
    console.log(`   ⚠️  Failed to fix ${file}:`, e.message);
  }
});

// Fix undefined variables in AdvancedScreener.jsx
console.log('2. Fixing undefined variables in AdvancedScreener.jsx...');
try {
  const file = 'src/pages/AdvancedScreener.jsx';
  if (fs.existsSync(file)) {
    let content = fs.readFileSync(file, 'utf8');
    
    // Add missing priceFilters state declaration
    const stateDeclarations = content.match(/const \[(\w+), set\w+\] = useState\([^)]*\);/g) || [];
    if (!content.includes('priceFilters') && !content.includes('setPriceFilters')) {
      // Find where to insert the state declaration
      const insertAfter = stateDeclarations[stateDeclarations.length - 1] || 'const [techFilters, setTechFilters] = useState({});';
      const insertion = insertAfter + '\n  const [priceFilters, setPriceFilters] = useState({});';
      content = content.replace(insertAfter, insertion);
    }
    
    fs.writeFileSync(file, content);
    console.log('   ✅ Fixed undefined variables in AdvancedScreener.jsx');
  }
} catch (e) {
  console.log('   ⚠️  Failed to fix AdvancedScreener.jsx:', e.message);
}

// Fix case declarations in OnboardingWizard.jsx
console.log('3. Fixing case block declarations in OnboardingWizard.jsx...');
try {
  const file = 'src/components/onboarding/OnboardingWizard.jsx';
  if (fs.existsSync(file)) {
    let content = fs.readFileSync(file, 'utf8');
    
    // Wrap case declarations in braces
    content = content.replace(/case\s+['"](\w+)['"]:\s*\n\s*(const\s+\w+\s*=)/g, 
      'case \'$1\': {\n      $2');
    content = content.replace(/case\s+['"](\w+)['"]:\s*\n\s*(let\s+\w+\s*=)/g, 
      'case \'$1\': {\n      $2');
    
    // Add closing braces for case blocks (look for break; or default:)
    content = content.replace(/(break;\s*\n)/g, '$1    }\n');
    
    fs.writeFileSync(file, content);
    console.log('   ✅ Fixed case declarations in OnboardingWizard.jsx');
  }
} catch (e) {
  console.log('   ⚠️  Failed to fix OnboardingWizard.jsx:', e.message);
}

console.log('🎉 Critical error fixes completed!');