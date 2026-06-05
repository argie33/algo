const { chromium } = require('playwright');
const https = require('https');

// Fetch CloudFront domain from AWS Secrets Manager or use env var
async function getCloudFrontDomain() {
  try {
    // Try to read from AWS Secrets Manager
    const { SecretsManager } = require('@aws-sdk/client-secrets-manager');
    const client = new SecretsManager({ region: 'us-east-1' });
    const secret = await client.getSecretValue({ SecretId: 'algo/cloudfront-domain' });
    const json = JSON.parse(secret.SecretString);
    return json.domain || json.cloudfront_domain;
  } catch (e) {
    console.log('Secrets Manager fallback: using env or default domain');
    return process.env.CLOUDFRONT_DOMAIN || null;
  }
}

(async () => {
  try {
    const domain = await getCloudFrontDomain();
    if (!domain) {
      console.error('❌ Cannot get CloudFront domain. Set CLOUDFRONT_DOMAIN env var or check AWS Secrets Manager');
      process.exit(1);
    }

    const awsUrl = `https://${domain}`;
    console.log(`🔍 Checking deployed site: ${awsUrl}`);

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    const errors = [];
    const warnings = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      } else if (msg.type() === 'warning') {
        warnings.push(msg.text());
      }
    });

    page.on('pageerror', error => {
      errors.push(`PAGE ERROR: ${error.message}`);
    });

    try {
      await page.goto(awsUrl, {
        waitUntil: 'networkidle',
        timeout: 20000
      });

      // Wait for any async errors
      await new Promise(resolve => setTimeout(resolve, 3000));

      console.log(`\n✅ Page loaded successfully`);
      console.log(`Total errors: ${errors.length}`);
      console.log(`Total warnings: ${warnings.length}`);

      if (errors.length > 0) {
        console.log('\n❌ ERRORS FOUND ON AWS:');
        errors.slice(0, 5).forEach((err, i) => {
          const msg = err.substring(0, 100);
          console.log(`  [${i + 1}] ${msg}`);
        });
        await browser.close();
        process.exit(1); // Exit with error to trigger fix loop
      } else {
        console.log('\n✅ NO ERRORS FOUND ON AWS SITE');
        await browser.close();
        process.exit(0);
      }
    } catch (e) {
      console.error(`⚠️ Navigation error: ${e.message}`);
      console.log('Site may be loading or network issue. Will retry on next loop.');
      await browser.close();
      process.exit(2); // Retry signal
    }
  } catch (error) {
    console.error('Fatal error:', error.message);
    process.exit(1);
  }
})();
