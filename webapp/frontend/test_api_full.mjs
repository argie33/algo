try {
  const response = await fetch('http://localhost:3001/api/algo/markets');
  const json = await response.json();

  console.log('Full response:');
  console.log(JSON.stringify(json, null, 2));

} catch (err) {
  console.error('Error:', err.message);
}
