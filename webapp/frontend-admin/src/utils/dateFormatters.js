/**
 * Shared date formatting utilities for chart components
 */

import { format } from "date-fns";

/**
 * Format a date string for display on chart X-axes
 * Returns formatted date like "Jan 15" or empty string if invalid
 * @param {string|Date} dateString - Date to format
 * @returns {string} Formatted date string (MMM dd) or original input if error
 */
export const formatXAxisDate = (dateString) => {
  if (!dateString) return "";
  try {
    return format(new Date(dateString), "MMM dd");
  } catch {
    return dateString;
  }
};

export default {
  formatXAxisDate,
};
