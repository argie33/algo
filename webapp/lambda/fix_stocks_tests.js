const fs = require("fs");

// Read the test file
const filePath = "./tests/unit/routes/stocks.test.js";
let content = fs.readFileSync(filePath, "utf8");

// Remove all mockQuery references and the lines containing them
const lines = content.split("\n");
const filteredLines = lines.filter((line) => {
  // Skip lines that contain mockQuery
  return !line.includes("mockQuery");
});

// Join the lines back together
const newContent = filteredLines.join("\n");

// Write back to file
fs.writeFileSync(filePath, newContent);

console.log("✅ Removed all mockQuery references from stocks test");
