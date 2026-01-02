/**
 * Export Utilities
 * Functions for exporting data to CSV and PDF formats
 */

/**
 * Export data to CSV format
 * @param {Array} data - Array of objects to export
 * @param {string} filename - Output filename (without extension)
 * @param {Array} columns - Array of column names (keys from data objects)
 */
export const exportToCSV = (data, filename = "export", columns = null) => {
  if (!data || data.length === 0) {
    console.warn("No data to export");
    return;
  }

  // Determine columns from first data object if not provided
  const cols = columns || Object.keys(data[0]);

  // Create CSV header
  const header = cols.map((col) => `"${col.replace(/"/g, '""')}"`).join(",");

  // Create CSV rows
  const rows = data.map((row) => {
    return cols
      .map((col) => {
        const value = row[col];
        // Handle null, undefined, and special characters
        if (value === null || value === undefined) {
          return '""';
        }
        // Quote and escape values containing quotes, commas, or newlines
        const stringValue = String(value);
        if (stringValue.includes(",") || stringValue.includes('"') || stringValue.includes("\n")) {
          return `"${stringValue.replace(/"/g, '""')}"`;
        }
        return `"${stringValue}"`;
      })
      .join(",");
  });

  // Combine header and rows
  const csv = [header, ...rows].join("\n");

  // Create blob and trigger download
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);

  link.setAttribute("href", url);
  link.setAttribute("download", `${filename}-${new Date().toISOString().split("T")[0]}.csv`);
  link.style.visibility = "hidden";

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

/**
 * Export data to JSON format
 * @param {Array|Object} data - Data to export
 * @param {string} filename - Output filename (without extension)
 */
export const exportToJSON = (data, filename = "export") => {
  if (!data) {
    console.warn("No data to export");
    return;
  }

  const json = JSON.stringify(data, null, 2);
  const blob = new Blob([json], { type: "application/json;charset=utf-8;" });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);

  link.setAttribute("href", url);
  link.setAttribute("download", `${filename}-${new Date().toISOString().split("T")[0]}.json`);
  link.style.visibility = "hidden";

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

/**
 * Export table HTML to PDF-like document
 * Creates a formatted HTML table for printing to PDF
 * @param {string} tableId - ID of the table HTML element to export
 * @param {string} filename - Output filename (without extension)
 * @param {string} title - Title for the document
 */
export const exportTableToPDF = (tableId, filename = "export", title = "Report") => {
  const table = document.getElementById(tableId);
  if (!table) {
    console.error(`Table with ID "${tableId}" not found`);
    return;
  }

  // Create a new window for printing
  const printWindow = window.open("", "", "width=900,height=600");
  if (!printWindow) {
    console.error("Failed to open print window. Please check popup blockers.");
    return;
  }

  // Get table content
  const tableHTML = table.outerHTML;

  // Create styled HTML for PDF
  const printContent = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <title>${title}</title>
      <style>
        body {
          font-family: Arial, sans-serif;
          margin: 20px;
          color: #333;
        }
        h1 {
          text-align: center;
          color: #1976d2;
          margin-bottom: 10px;
        }
        .export-date {
          text-align: center;
          color: #999;
          font-size: 12px;
          margin-bottom: 20px;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          margin-top: 20px;
        }
        th {
          background-color: #1976d2;
          color: white;
          padding: 12px;
          text-align: left;
          font-weight: bold;
          border: 1px solid #1976d2;
        }
        td {
          padding: 10px 12px;
          border: 1px solid #ddd;
        }
        tr:nth-child(even) {
          background-color: #f9f9f9;
        }
        tr:hover {
          background-color: #f5f5f5;
        }
        @media print {
          body {
            margin: 0;
            padding: 10px;
          }
          table {
            page-break-inside: avoid;
          }
        }
      </style>
    </head>
    <body>
      <h1>${title}</h1>
      <div class="export-date">Exported on ${new Date().toLocaleString()}</div>
      ${tableHTML}
    </body>
    </html>
  `;

  // Write content to print window
  printWindow.document.write(printContent);
  printWindow.document.close();

  // Trigger print dialog
  setTimeout(() => {
    printWindow.print();
  }, 250);
};

/**
 * Export HTML table directly to CSV (simpler version for table data)
 * @param {string} tableId - ID of the table HTML element
 * @param {string} filename - Output filename
 */
export const tableToCSV = (tableId, filename = "export") => {
  const table = document.getElementById(tableId);
  if (!table) {
    console.error(`Table with ID "${tableId}" not found`);
    return;
  }

  let csv = [];
  const rows = table.querySelectorAll("tr");

  rows.forEach((row) => {
    let rowData = [];
    const cells = row.querySelectorAll("td, th");

    cells.forEach((cell) => {
      // Get text content and escape quotes
      let cellText = cell.textContent.trim();
      cellText = cellText.replace(/"/g, '""');
      rowData.push(`"${cellText}"`);
    });

    csv.push(rowData.join(","));
  });

  // Create blob and trigger download
  const csvContent = csv.join("\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);

  link.setAttribute("href", url);
  link.setAttribute("download", `${filename}-${new Date().toISOString().split("T")[0]}.csv`);
  link.style.visibility = "hidden";

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

/**
 * Format data for export
 * Removes sensitive fields and formats dates
 * @param {Array} data - Data to format
 * @param {Array} excludeFields - Fields to exclude from export
 */
export const formatDataForExport = (data, excludeFields = []) => {
  return data.map((item) => {
    const formatted = { ...item };
    // Remove excluded fields
    excludeFields.forEach((field) => {
      delete formatted[field];
    });
    return formatted;
  });
};
