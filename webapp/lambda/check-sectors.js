const { query } = require('./utils/database');

(async () => {
  try {
    process.env.DB_HOST = 'localhost';
    process.env.DB_PORT = '5432';
    process.env.DB_USER = 'stocks';
    process.env.DB_PASSWORD = 'bed0elAn';
    process.env.DB_NAME = 'stocks';
    process.env.DB_SSL = 'false';

    console.log('\n🔍 SECTOR & INDUSTRY ANALYSIS:\n');

    // Check distinct sectors
    const sectorsResult = await query(`SELECT DISTINCT sector_name FROM sector_ranking WHERE sector_name IS NOT NULL ORDER BY sector_name`);
    console.log(`Distinct sectors in sector_ranking: ${sectorsResult?.rows?.length || 0}`);
    if (sectorsResult?.rows?.length <= 20) {
      sectorsResult?.rows?.forEach(r => console.log(`  - ${r.sector_name}`));
    }

    // Check distinct industries
    const industriesResult = await query(`SELECT DISTINCT industry FROM industry_ranking WHERE industry IS NOT NULL ORDER BY industry`);
    console.log(`\nDistinct industries in industry_ranking: ${industriesResult?.rows?.length || 0}`);
    if (industriesResult?.rows?.length <= 20) {
      industriesResult?.rows?.forEach(r => console.log(`  - ${r.industry}`));
    }

    // Check distinct sectors from company_profile
    const companySectorsResult = await query(`SELECT DISTINCT sector FROM company_profile WHERE sector IS NOT NULL ORDER BY sector`);
    console.log(`\nDistinct sectors in company_profile: ${companySectorsResult?.rows?.length || 0}`);
    if (companySectorsResult?.rows?.length <= 20) {
      companySectorsResult?.rows?.forEach(r => console.log(`  - ${r.sector}`));
    }

    console.log('\n');
  } catch (err) {
    console.error('Error:', err.message);
    throw err;
  }
})().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
