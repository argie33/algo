const r = await fetch('http://localhost:3001/api/algo/equity-curve?limit=10');
const json = await r.json();
console.log('Keys:', Object.keys(json));
console.log('data field type:', typeof json.data, Array.isArray(json.data));
if (json.data) {
  console.log('data keys:', Object.keys(json.data));
  if (json.data.items) {
    console.log('data.items count:', json.data.items.length);
    if (json.data.items.length > 0) {
      console.log('First item:', JSON.stringify(json.data.items[0]));
    }
  }
}
// Check what list_response actually returns
const r2 = await fetch('http://localhost:3001/api/algo/notifications');
const j2 = await r2.json();
console.log('\n=== NOTIFICATIONS (list_response) ===');
console.log('Keys:', Object.keys(j2));
console.log('data keys:', Object.keys(j2.data || {}));
