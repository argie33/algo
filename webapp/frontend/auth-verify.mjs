import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'fs';
import { join } from 'path';

const outDir = 'C:\\Users\\arger\\AppData\\Local\\Temp\\auth-screenshots';
try { mkdirSync(outDir, { recursive: true }); } catch {}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const results = [];

// ---- LOGIN FORM ----
await page.goto('http://localhost:5173/login', { waitUntil: 'domcontentloaded', timeout: 15000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: join(outDir, '1-login-page.png') });

const emailLabel = await page.textContent('label[for="username"]').catch(() => null);
results.push({ check: 'login-email-label', value: emailLabel?.trim() });

const inputType = await page.getAttribute('#username', 'type').catch(() => null);
results.push({ check: 'login-input-type', value: inputType });

const loginPlaceholder = await page.getAttribute('#username', 'placeholder').catch(() => null);
results.push({ check: 'login-placeholder', value: loginPlaceholder });

// ---- REGISTER FORM ----
const signUpBtn = await page.$('button:has-text("Sign up")');
if (signUpBtn) {
  await signUpBtn.click();
  await page.waitForTimeout(800);
}
await page.screenshot({ path: join(outDir, '2-register-form.png') });

const usernameField = await page.$('#username').catch(() => null);
results.push({ check: 'register-no-username-field', value: usernameField === null ? 'PASS - no username field' : 'FAIL - username field still present' });

const emailField = await page.$('#email').catch(() => null);
results.push({ check: 'register-email-field-exists', value: emailField !== null ? 'PASS' : 'FAIL' });

// Type full password and confirm focus is not lost
if (emailField) {
  const pwField = await page.$('#password');
  if (pwField) {
    await pwField.click();
    // Type full string without delay to reproduce the bug
    await page.keyboard.type('MyPassword123!@', { delay: 30 });
    await page.waitForTimeout(300);
    const pwValue = await page.inputValue('#password').catch(() => null);
    results.push({
      check: 'register-password-full-type',
      value: pwValue === 'MyPassword123!@'
        ? `PASS - full value typed correctly: "${pwValue}"`
        : `FAIL - expected "MyPassword123!@", got "${pwValue}"`
    });
    const focused = await page.evaluate(() => document.activeElement?.id);
    results.push({ check: 'register-password-focus', value: `active element after typing: "${focused}"` });
  }
}

await page.screenshot({ path: join(outDir, '3-register-after-typing.png') });

// ---- LOGIN TYPING TEST ----
const signInBtn = await page.$('button:has-text("Sign in")');
if (signInBtn) {
  await signInBtn.click();
  await page.waitForTimeout(500);
}

const loginEmailInput = await page.$('#username');
if (loginEmailInput) {
  await loginEmailInput.click();
  await page.keyboard.type('argeropolos@gmail.com', { delay: 20 });
  const emailVal = await page.inputValue('#username').catch(() => null);
  results.push({
    check: 'login-email-full-type',
    value: emailVal === 'argeropolos@gmail.com'
      ? `PASS - "${emailVal}"`
      : `FAIL - got "${emailVal}"`
  });
}

const loginPwInput = await page.$('#password');
if (loginPwInput) {
  await loginPwInput.click();
  await page.keyboard.type('SomePass123!', { delay: 20 });
  const pwVal = await page.inputValue('#password').catch(() => null);
  results.push({
    check: 'login-password-full-type',
    value: pwVal === 'SomePass123!' ? 'PASS' : `FAIL - got "${pwVal}"`
  });
}

await page.screenshot({ path: join(outDir, '4-login-filled.png') });

await browser.close();
console.log(JSON.stringify(results, null, 2));
console.log('\nScreenshots:', outDir);
