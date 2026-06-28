try {
  const response = await fetch('http://localhost:3001/api/algo/markets');
  const json = await response.json();

  console.log('Response status:', response.status);
  console.log('Response structure:');
  console.log('  - success:', json.success);
  console.log('  - statusCode:', json.statusCode);
  console.log('  - has data:', !!json.data);
  console.log('  - data_error:', json.data?.data_error);
  console.log('  - market_health exists:', !!json.data?.market_health);

  if (json.data?.market_health) {
    console.log('  - market_health keys:', Object.keys(json.data.market_health));
    console.log('  - market_health.date:', json.data.market_health.date);
  } else {
    console.log('  - market_health is:', json.data?.market_health);
  }

  // Simulate frontend check
  const m = json.data || json;
  const hasDataUnavailability = json.data_error || !m.market_health;
  console.log('\nFrontend check:');
  console.log('  - hasDataUnavailability:', hasDataUnavailability);
  console.log('  - (data_error check):', json.data_error);
  console.log('  - (!m.market_health check):', !m.market_health);

} catch (err) {
  console.error('Error:', err.message);
}
