/**
 * XSS Protection Utilities
 * Sanitize user-provided data to prevent cross-site scripting attacks
 */

/**
 * Sanitize text to remove potentially harmful HTML/JS
 * @param {string} text - Text to sanitize
 * @returns {string} Sanitized text safe for display
 */
export function sanitizeText(text) {
  if (!text || typeof text !== "string") {
    return "";
  }

  const map = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };

  return text.replace(/[&<>"']/g, (char) => map[char]);
}

/**
 * Validate and sanitize URLs (prevent javascript: protocol)
 * @param {string} url - URL to validate
 * @returns {string|null} Sanitized URL or null if invalid
 */
export function sanitizeUrl(url) {
  if (!url || typeof url !== "string") {
    return null;
  }

  // Remove leading/trailing whitespace
  url = url.trim();

  // Reject javascript: and data: protocols
  if (
    url.toLowerCase().startsWith("javascript:") ||
    url.toLowerCase().startsWith("data:")
  ) {
    return null;
  }

  // Only allow http, https, and relative URLs
  if (
    !url.startsWith("http://") &&
    !url.startsWith("https://") &&
    !url.startsWith("/")
  ) {
    return null;
  }

  return url;
}

/**
 * Sanitize an object (deep sanitize all string values)
 * @param {object} obj - Object to sanitize
 * @returns {object} Sanitized object
 */
export function sanitizeObject(obj) {
  if (!obj || typeof obj !== "object") {
    return obj;
  }

  if (Array.isArray(obj)) {
    return obj.map((item) => sanitizeObject(item));
  }

  const sanitized = {};
  for (const [key, value] of Object.entries(obj)) {
    if (typeof value === "string") {
      sanitized[key] = sanitizeText(value);
    } else if (typeof value === "object" && value !== null) {
      sanitized[key] = sanitizeObject(value);
    } else {
      sanitized[key] = value;
    }
  }

  return sanitized;
}

/**
 * Validate input as safe number (prevents NaN injection)
 * @param {any} value - Value to validate
 * @param {number} min - Minimum allowed value
 * @param {number} max - Maximum allowed value
 * @returns {number|null} Valid number or null
 */
export function sanitizeNumber(value, min = -Infinity, max = Infinity) {
  const num = Number(value);
  if (isNaN(num)) {
    return null;
  }
  if (num < min || num > max) {
    return null;
  }
  return num;
}

export default {
  sanitizeText,
  sanitizeUrl,
  sanitizeObject,
  sanitizeNumber,
};
