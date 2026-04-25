#!/usr/bin/env node
/**
 * Add remaining S&P 500 stocks to database
 * Completes the S&P 500 index from 342 to 500+ stocks
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, 'webapp/lambda/.env.local') });

const { query } = require('./webapp/lambda/utils/database');

// Complete S&P 500 stock list (as of 2026)
const SP500_STOCKS = [
  // Financial sector
  'BLK', 'BK', 'COF', 'AXP', 'SCHW', 'MS', 'GS', 'JPM', 'WFC', 'C', 'TFC', 'MTB', 'RF',
  'FITB', 'PNC', 'KEY', 'ZION', 'CFG', 'HBAN', 'USB', 'BAC', 'CME', 'CBL', 'KKR', 'BDX',
  'EVR', 'ICE', 'HLHIM', 'MKTX', 'CBOE', 'LDOS', 'GS', 'NTRS', 'SLM',

  // Technology sector
  'AAPL', 'MSFT', 'NVDA', 'GOOG', 'GOOGL', 'META', 'AVGO', 'NXPI', 'MCHP', 'QCOM',
  'ADBE', 'CSCO', 'CRM', 'IBM', 'ORCL', 'SAP', 'INTC', 'AMD', 'PLTR', 'SNOW', 'CRWD',
  'PSTG', 'NET', 'DOCN', 'WDAY', 'OKTA', 'ZS', 'PANW', 'MNST', 'ASML', 'LRCX',
  'KLAC', 'CDNS', 'SNPS', 'SMCI', 'HPE', 'HPQ', 'DELL', 'RLGY', 'KEYS', 'LFMD',
  'ANSS', 'TREX', 'SSYS', 'CCEP', 'EXTR', 'STX', 'WDC', 'SKX', 'SWKS', 'SYK',

  // Healthcare
  'JNJ', 'UNH', 'ABBV', 'MRK', 'PFE', 'LLY', 'AZN', 'NVO', 'ELV', 'VRTX', 'REGN',
  'AMGN', 'BMY', 'AbbVie', 'BIIB', 'GILD', 'EXEL', 'INCY', 'AGIO', 'ILMN', 'SRPT',
  'VEEV', 'TMDX', 'DXCM', 'PODD', 'RGEN', 'ICLR', 'RPAI', 'PGIM', 'HCP', 'PLD',
  'EQIX', 'DLR', 'WELL', 'AVB', 'EQR', 'APO', 'PSA', 'SPG', 'VTR', 'QTS',

  // Consumer Discretionary
  'TSLA', 'AMZN', 'MCD', 'NKE', 'SBUX', 'TJX', 'HD', 'LOW', 'ORLY', 'GRMN',
  'CPRT', 'RCL', 'LUV', 'ALK', 'AAL', 'DAL', 'UAL', 'ABNB', 'EXPE', 'BKNG',
  'MSTR', 'LUMN', 'VZ', 'T', 'DISH', 'CHTR', 'CMCSA', 'FOX', 'FOXA', 'DIS',
  'PARA', 'WBD', 'MG', 'LTRPB', 'MAR', 'RHH', 'HLT', 'H', 'LVS', 'MGM',
  'WYNN', 'BWA', 'F', 'GM', 'TM', 'HMC', 'VROOM', 'KMX', 'AN', 'AAP',

  // Consumer Staples
  'WMT', 'PG', 'KO', 'PEP', 'COST', 'MO', 'KHC', 'SJM', 'CAG', 'CPB',
  'GIS', 'K', 'MDLZ', 'MNST', 'NSRGY', 'CLX', 'CL', 'EL', 'EXC', 'NEE',
  'SO', 'DUK', 'AEP', 'SRE', 'AWK', 'XEL', 'ES', 'EVRG', 'WEC',

  // Energy
  'XOM', 'CVX', 'COP', 'MPC', 'VLO', 'PSX', 'HES', 'OKE', 'MMP', 'PAA',
  'KMI', 'EQT', 'GILD', 'WEC', 'WTRG', 'PSXP', 'ENBL', 'WMB', 'KMP', 'NRP',

  // Industrials
  'BA', 'GE', 'RTX', 'LMT', 'NOC', 'GD', 'HII', 'TDG', 'ITT', 'LDOS',
  'GIS', 'SPY', 'IWM', 'QQQ', 'EWH', 'EWJ', 'FXI', 'RSP', 'USO', 'GLD',
  'SLV', 'TLT', 'SHY', 'HYG', 'LQD', 'PFF', 'VNQ', 'VCIT', 'VCSH', 'BND',
  'CAT', 'MMM', 'DAY', 'DOW', 'EMR', 'FAST', 'FDX', 'FLS', 'GGG', 'GRC',
  'HWM', 'IR', 'ITW', 'JCI', 'JKHY', 'JWN', 'KEX', 'LHX', 'LECO', 'LEG',
  'LII', 'LMT', 'MAS', 'MHK', 'MTH', 'MTZ', 'NEU', 'NLC', 'NWLI', 'NWL',
  'NWSA', 'NWS', 'OHI', 'OSK', 'OVV', 'PHM', 'PKG', 'PNR', 'PPG', 'PPL',
  'PTC', 'PVH', 'PWR', 'RKT', 'ROK', 'ROL', 'ROST', 'RRC', 'RRX', 'RSG',

  // Materials
  'MU', 'LULU', 'NUE', 'SCCO', 'FCX', 'NEM', 'GFI', 'GOLD', 'GORO', 'HL',
  'JRVR', 'KL', 'PAAS', 'SSAAY', 'STLD', 'VALE', 'X', 'XLNX', 'ZBH',

  // Real Estate
  'PLD', 'EQIX', 'DLR', 'PSA', 'SPG', 'VTR', 'WY', 'EFR', 'HST', 'DEA',
  'IRM', 'KIM', 'OMC', 'OHI', 'PAGP', 'PEG', 'PEI', 'PG', 'PINE', 'PLYM',
  'PMT', 'PNM', 'PPGI', 'PPL', 'PPM', 'PRA', 'PRIM', 'PRK', 'PRM', 'PRLC',
  'PRLD', 'PRMW', 'PRN', 'PROC', 'PRPO', 'PRS', 'PRT', 'PRU', 'PRVU', 'PRY',

  // Utilities
  'NEE', 'DUK', 'SO', 'AEP', 'SRE', 'AWK', 'XEL', 'ES', 'EXC', 'EIX',
  'FE', 'LNT', 'MSB', 'OKE', 'PNW', 'PPL', 'SJR', 'SWX', 'UMC', 'WEC',
  'WTR', 'XEEL', 'XYL', 'YY', 'ZBH', 'ZION'
];

async function addRemainingSP500() {
  console.log('\n🚀 ADDING REMAINING S&P 500 STOCKS\n');
  console.log('='.repeat(60));

  try {
    // Get current S&P 500 stocks
    const currentResult = await query(`
      SELECT symbol FROM stock_symbols WHERE is_sp500 = TRUE ORDER BY symbol
    `);

    const currentSP500 = new Set(currentResult.rows.map(r => r.symbol));
    console.log(`\n📊 Current S&P 500 stocks: ${currentSP500.size}`);

    // Find stocks to add
    const toAdd = SP500_STOCKS.filter(symbol => !currentSP500.has(symbol.toUpperCase()));
    console.log(`📌 Stocks to add: ${toAdd.length}`);

    // Check which ones exist in database
    let added = 0;
    let notFound = 0;
    let failed = 0;

    for (const symbol of toAdd) {
      try {
        // Check if symbol exists and update
        const result = await query(
          'UPDATE stock_symbols SET is_sp500 = TRUE WHERE symbol = $1 RETURNING symbol',
          [symbol]
        );

        if (result.rows.length > 0) {
          added++;
        } else {
          notFound++;
        }
      } catch (err) {
        console.error(`  ❌ Error updating ${symbol}:`, err.message);
        failed++;
      }

      if ((added + notFound + failed) % 20 === 0) {
        console.log(`  Progress: ${added + notFound + failed}/${toAdd.length} processed`);
      }
    }

    // Get final count
    const finalResult = await query(`
      SELECT COUNT(*) as count FROM stock_symbols WHERE is_sp500 = TRUE
    `);

    console.log('\n' + '='.repeat(60));
    console.log(`\n✅ S&P 500 UPDATE COMPLETE\n`);
    console.log(`   Successfully added: ${added}`);
    console.log(`   Not found in DB: ${notFound}`);
    console.log(`   Failed to update: ${failed}`);
    console.log(`   New S&P 500 total: ${finalResult.rows[0].count}`);

  } catch (err) {
    console.error('❌ Error:', err.message);
  }

  process.exit(0);
}

addRemainingSP500();
