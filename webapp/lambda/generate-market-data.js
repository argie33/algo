#!/usr/bin/env node
/**
 * Generate comprehensive market data from real database
 * Pulls sector/industry rankings and performance from actual data
 * Writes to /tmp/comprehensive_market_data.json for API consumption
 */

const fs = require('fs');
const path = require('path');
const { query } = require('./utils/database');

const OUTPUT_PATH = process.platform === 'win32'
  ? path.join(process.env.TEMP || 'C:\\temp', 'comprehensive_market_data.json')
  : '/tmp/comprehensive_market_data.json';

async function generateMarketData() {
  try {
    console.log('📊 Generating real market data from database...\n');

    // 1. Get latest sector data
    console.log('[1/4] Fetching sector rankings...');
    const sectorsResult = await query(`
      SELECT DISTINCT ON (sector_name)
        sector_name,
        current_rank,
        momentum_score,
        date_recorded
      FROM sector_ranking
      WHERE sector_name IS NOT NULL AND TRIM(sector_name) != ''
      ORDER BY sector_name, date_recorded DESC
      LIMIT 100
    `);

    const sectors = {};
    if (sectorsResult?.rows) {
      sectorsResult.rows.forEach((row, idx) => {
        const key = row.sector_name.toLowerCase().replace(/\s+/g, '-');
        sectors[key] = {
          name: row.sector_name,
          symbol: row.sector_name.substring(0, 3).toUpperCase(),
          rank: row.current_rank || (idx + 1),
          momentum: row.momentum_score || 0,
          date: row.date_recorded ? row.date_recorded.toISOString().split('T')[0] : new Date().toISOString().split('T')[0]
        };
      });
    }
    console.log(`   ✅ Found ${Object.keys(sectors).length} sectors\n`);

    // 2. Get latest industry data
    console.log('[2/4] Fetching industry rankings...');
    const industriesResult = await query(`
      SELECT DISTINCT ON (industry)
        industry,
        current_rank,
        momentum_score,
        stock_count,
        date_recorded
      FROM industry_ranking
      WHERE industry IS NOT NULL AND TRIM(industry) != ''
      ORDER BY industry, date_recorded DESC
      LIMIT 200
    `);

    const industries = {};
    if (industriesResult?.rows) {
      industriesResult.rows.forEach((row, idx) => {
        const key = row.industry.toLowerCase().replace(/\s+/g, '-');
        industries[key] = {
          name: row.industry,
          symbol: row.industry.substring(0, 3).toUpperCase(),
          rank: row.current_rank || (idx + 1),
          momentum: row.momentum_score || 0,
          stock_count: row.stock_count || 0,
          date: row.date_recorded ? row.date_recorded.toISOString().split('T')[0] : new Date().toISOString().split('T')[0]
        };
      });
    }
    console.log(`   ✅ Found ${Object.keys(industries).length} industries\n`);

    // 3. Get sector performance data
    console.log('[3/4] Fetching sector performance...');
    const sectorPerfResult = await query(`
      SELECT DISTINCT ON (sector)
        sector,
        performance_1d,
        performance_5d,
        performance_20d,
        performance_ytd,
        date
      FROM sector_performance
      WHERE sector IS NOT NULL
      ORDER BY sector, date DESC
      LIMIT 100
    `);

    if (sectorPerfResult?.rows) {
      sectorPerfResult.rows.forEach(row => {
        const key = row.sector.toLowerCase().replace(/\s+/g, '-');
        if (sectors[key]) {
          sectors[key].performance_1d = row.performance_1d || 0;
          sectors[key].performance_5d = row.performance_5d || 0;
          sectors[key].performance_20d = row.performance_20d || 0;
          sectors[key].performance_ytd = row.performance_ytd || 0;
        }
      });
    }
    console.log(`   ✅ Updated sector performance data\n`);

    // 4. Get industry performance data
    console.log('[4/4] Fetching industry performance...');
    const industryPerfResult = await query(`
      SELECT DISTINCT ON (industry)
        industry,
        performance_1d,
        performance_5d,
        performance_20d,
        performance_ytd,
        date
      FROM industry_performance
      WHERE industry IS NOT NULL
      ORDER BY industry, date DESC
      LIMIT 200
    `);

    if (industryPerfResult?.rows) {
      industryPerfResult.rows.forEach(row => {
        const key = row.industry.toLowerCase().replace(/\s+/g, '-');
        if (industries[key]) {
          industries[key].performance_1d = row.performance_1d || 0;
          industries[key].performance_5d = row.performance_5d || 0;
          industries[key].performance_20d = row.performance_20d || 0;
          industries[key].performance_ytd = row.performance_ytd || 0;
        }
      });
    }
    console.log(`   ✅ Updated industry performance data\n`);

    // 5. Build comprehensive data object
    const comprehensiveData = {
      timestamp: new Date().toISOString(),
      generated_at: new Date().toISOString(),
      source: 'database',
      sectors: sectors,
      industries: industries,
      metadata: {
        sector_count: Object.keys(sectors).length,
        industry_count: Object.keys(industries).length,
        has_performance: true,
        has_momentum: true
      }
    };

    // 6. Write to JSON file
    console.log(`💾 Writing data to ${OUTPUT_PATH}...`);
    const outputDir = path.dirname(OUTPUT_PATH);
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }
    fs.writeFileSync(OUTPUT_PATH, JSON.stringify(comprehensiveData, null, 2));
    console.log('✅ Market data generated successfully\n');

    // 7. Log summary
    console.log('='.repeat(60));
    console.log('📊 MARKET DATA GENERATION COMPLETE');
    console.log('='.repeat(60));
    console.log(`Sectors:      ${Object.keys(sectors).length}`);
    console.log(`Industries:   ${Object.keys(industries).length}`);
    console.log(`Timestamp:    ${comprehensiveData.timestamp}`);
    console.log(`Location:     ${OUTPUT_PATH}`);
    console.log('='.repeat(60));

    process.exit(0);

  } catch (error) {
    console.error('❌ Error generating market data:', error.message);
    console.error(error);
    process.exit(1);
  }
}

generateMarketData();
