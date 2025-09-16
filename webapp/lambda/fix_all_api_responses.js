const fs = require("fs");
const path = require("path");

// Function to fix ALL API response inconsistencies
function fixAllApiResponses(content) {
  // Fix res.error() patterns to proper res.status().json()
  content = content.replace(
    /res\.error\(\s*"([^"]+)"\s*,\s*(\d+)\s*,?\s*(\{[^}]*\})?\s*\)/g,
    (match, message, code, options) => {
      const optionsStr = options
        ? `, ${options.replace(/^{/, "").replace(/}$/, "")}`
        : "";
      return `res.status(${code}).json({success: false, error: "${message}"${optionsStr}})`;
    }
  );

  // Fix res.error() without status code (default to 500)
  content = content.replace(
    /res\.error\(\s*"([^"]+)"\s*,?\s*(\{[^}]*\})?\s*\)/g,
    (match, message, options) => {
      const optionsStr = options
        ? `, ${options.replace(/^{/, "").replace(/}$/, "")}`
        : "";
      return `res.status(500).json({success: false, error: "${message}"${optionsStr}})`;
    }
  );

  // Fix res.success() patterns to proper res.json()
  content = content.replace(
    /res\.success\(\s*\{([^}]*)\}\s*,?\s*(\d+)?\s*,?\s*(\{[^}]*\})?\s*\)/g,
    (match, data, code, options) => {
      const statusCode = code || "200";
      const optionsStr = options
        ? `, ${options.replace(/^{/, "").replace(/}$/, "")}`
        : "";
      return `res.status(${statusCode}).json({success: true, ${data}${optionsStr}})`;
    }
  );

  // Fix res.success() with just data
  content = content.replace(
    /res\.success\(\s*([^,)]+)\s*,?\s*(\d+)?\s*,?\s*(\{[^}]*\})?\s*\)/g,
    (match, data, code, options) => {
      const statusCode = code || "200";
      const optionsStr = options
        ? `, ${options.replace(/^{/, "").replace(/}$/, "")}`
        : "";
      return `res.status(${statusCode}).json({success: true, data: ${data}${optionsStr}})`;
    }
  );

  return content;
}

// Get ALL route files
const routeFiles = fs
  .readdirSync(path.join(__dirname, "routes"))
  .filter((file) => file.endsWith(".js"))
  .filter((file) => !file.includes(".backup"));

let totalFixed = 0;
let filesModified = 0;

console.log(`🔧 Fixing API responses in ${routeFiles.length} route files...`);

routeFiles.forEach((fileName) => {
  const filePath = path.join(__dirname, "routes", fileName);
  try {
    let content = fs.readFileSync(filePath, "utf8");
    const originalContent = content;
    content = fixAllApiResponses(content);

    if (content !== originalContent) {
      fs.writeFileSync(filePath, content);
      const errorMatches = (
        originalContent.match(/res\.(error|success)\(/g) || []
      ).length;
      totalFixed += errorMatches;
      filesModified++;
      console.log(
        `✅ Fixed ${errorMatches} API responses in routes/${fileName}`
      );
    }
  } catch (error) {
    console.error(`❌ Error processing ${fileName}:`, error.message);
  }
});

console.log(
  `\n📊 Summary: Fixed ${totalFixed} API responses across ${filesModified} files`
);
console.log("🎉 ALL API response fixes completed!");
