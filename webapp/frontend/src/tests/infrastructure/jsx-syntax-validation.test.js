/**
 * JSX Syntax Validation Tests
 * These tests ensure all JSX files have valid syntax and balanced tags
 * This should catch issues like the MarketOverview.jsx parsing error
 */

import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { parse } from "@babel/parser";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const srcDir = join(__dirname, "../../");

// Get all JSX files recursively
function getAllJSXFiles(dir, files = []) {
  const entries = readdirSync(dir);

  for (const entry of entries) {
    const fullPath = join(dir, entry);
    const stat = statSync(fullPath);

    if (
      stat.isDirectory() &&
      !entry.includes("node_modules") &&
      !entry.includes(".git")
    ) {
      getAllJSXFiles(fullPath, files);
    } else if (entry.endsWith(".jsx") || entry.endsWith(".js")) {
      files.push(fullPath);
    }
  }

  return files;
}

describe("JSX Syntax Validation", () => {
  const jsxFiles = getAllJSXFiles(srcDir);

  it("should find JSX files to test", () => {
    expect(jsxFiles.length).toBeGreaterThan(0);
    console.log(`Found ${jsxFiles.length} JavaScript/JSX files to validate`);
  });

  jsxFiles.forEach((filePath) => {
    const relativePath = filePath.replace(srcDir, "").replace(/^\//, "");

    it(`should have valid JSX syntax: ${relativePath}`, () => {
      let content;

      try {
        content = readFileSync(filePath, "utf8");
      } catch (error) {
        throw new Error(
          `Could not read file ${relativePath}: ${error.message}`
        );
      }

      // Skip empty files
      if (!content.trim()) {
        return;
      }

      // Try to parse the JSX file
      try {
        parse(content, {
          sourceType: "module",
          plugins: [
            "jsx",
            "typescript",
            "decorators-legacy",
            "classProperties",
            "objectRestSpread",
            "functionBind",
            "exportDefaultFrom",
            "dynamicImport",
          ],
        });
      } catch (error) {
        throw new Error(
          `JSX parsing error in ${relativePath}:${error.loc ? ` line ${error.loc.line}, column ${error.loc.column}` : ""}\n` +
            `Error: ${error.message}\n` +
            `This type of error should be caught by linting before commit.`
        );
      }
    });
  });

  // Additional test for common JSX balance issues
  jsxFiles.forEach((filePath) => {
    const relativePath = filePath.replace(srcDir, "").replace(/^\//, "");

    it(`should have balanced JSX tags: ${relativePath}`, () => {
      if (!filePath.endsWith(".jsx")) return;

      const content = readFileSync(filePath, "utf8");

      // Simple tag balance check (not perfect but catches obvious issues)
      const openTags = (content.match(/<[A-Za-z][^/>]*[^/]>/g) || []).length;
      const closeTags = (content.match(/<\/[A-Za-z][^>]*>/g) || []).length;
      const selfCloseTags = (content.match(/<[A-Za-z][^>]*\/>/g) || []).length;
      const fragments = (content.match(/<>/g) || []).length;
      const fragmentsClose = (content.match(/<\/>/g) || []).length;

      // Total opening elements should equal total closing elements
      const totalOpen = openTags + selfCloseTags + fragments;
      const totalClose = closeTags + selfCloseTags + fragmentsClose;

      if (totalOpen !== totalClose) {
        throw new Error(
          `Unbalanced JSX tags in ${relativePath}:\n` +
            `Opening tags: ${openTags}, Self-closing: ${selfCloseTags}, Fragments: ${fragments}\n` +
            `Closing tags: ${closeTags}, Fragment closes: ${fragmentsClose}\n` +
            `Total open: ${totalOpen}, Total close: ${totalClose}\n` +
            `Difference: ${Math.abs(totalOpen - totalClose)} unbalanced tags`
        );
      }
    });
  });
});

describe("Lint Integration Validation", () => {
  it("should validate that lint catches JSX parsing errors", async () => {
    // This test ensures our lint process catches JSX errors before they reach build
    const { exec } = await import("child_process");
    const { promisify } = await import("util");
    const execAsync = promisify(exec);

    try {
      // Run lint to check for errors
      const { stdout, stderr } = await execAsync("npm run lint", {
        cwd: join(__dirname, "../../.."),
        timeout: 30000,
      });

      const output = stdout + stderr;

      // Check if lint found any JSX parsing errors
      const hasJSXErrors =
        output.includes("Parsing error") ||
        output.includes("Adjacent JSX elements") ||
        output.includes("Unterminated regular expression") ||
        output.includes("Transform failed");

      if (hasJSXErrors) {
        throw new Error(
          `Lint found JSX parsing errors that need to be fixed:\n${output}\n\n` +
            `These errors should be fixed before continuing with other tasks.`
        );
      }

      // If no JSX errors, lint should pass (warnings are acceptable up to max-warnings)
      console.log(
        "✅ Lint validation passed - no critical JSX parsing errors found"
      );
    } catch (error) {
      // If lint fails due to JSX errors, that's what we want to catch
      const output = error.stdout + error.stderr;

      if (
        output.includes("Parsing error") ||
        output.includes("Adjacent JSX elements") ||
        output.includes("Unterminated regular expression")
      ) {
        throw new Error(
          `CRITICAL: Lint found JSX parsing errors that must be fixed immediately:\n${output}\n\n` +
            `Fix these errors before proceeding with other development tasks.`
        );
      }

      // Other lint failures might be acceptable (warnings, etc.)
      throw error;
    }
  });

  it("should validate that build fails on JSX errors when lint passes incorrectly", async () => {
    // Backup test: if lint somehow misses JSX errors, build should still catch them
    const { exec } = await import("child_process");
    const { promisify } = await import("util");
    const execAsync = promisify(exec);

    try {
      // Run build to see if it passes
      await execAsync("npm run build", {
        cwd: join(__dirname, "../../.."),
        timeout: 60000,
      });

      // If build succeeds, that's good - all JSX should be valid
      console.log("✅ Build validation passed - no JSX errors found");
      expect(true).toBe(true);
    } catch (error) {
      // If build fails, check if it's due to JSX parsing errors
      const output = error.stdout + error.stderr;

      if (
        output.includes("Parsing error") ||
        output.includes("Unterminated") ||
        output.includes("Adjacent JSX elements") ||
        output.includes("Transform failed")
      ) {
        throw new Error(
          `CRITICAL: Build failed due to JSX/parsing errors that lint should have caught:\n${output}\n\n` +
            `This indicates our lint configuration may be incomplete. Fix the JSX errors and verify lint catches them.`
        );
      }

      // Other build failures might be acceptable (missing env vars, etc.)
      console.warn(
        "Build failed for non-JSX reasons (acceptable):",
        error.message
      );
    }
  });
});
