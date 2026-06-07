/**
 * CSV export utility with RFC 4180 compliant escaping.
 * Generates a UTF-8 encoded CSV and triggers a browser download.
 */

/**
 * Escapes a cell value per RFC 4180:
 * - If the value contains a comma, double-quote, or newline, wrap it in double quotes
 * - Any double-quote characters within the value are escaped by doubling them
 */
export function escapeCSVField(value: unknown): string {
  const str = value == null ? '' : String(value);
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

/**
 * Converts a 2D data array with headers into an RFC 4180 compliant CSV string.
 * @param headers - Column header names (first row of the CSV)
 * @param rows - 2D array of cell values
 * @returns UTF-8 encoded CSV string with CRLF line endings per RFC 4180
 */
export function buildCSVString(headers: string[], rows: unknown[][]): string {
  const headerRow = headers.map(escapeCSVField).join(',');
  const dataRows = rows.map(row => row.map(escapeCSVField).join(','));
  return [headerRow, ...dataRows].join('\r\n');
}

/**
 * Exports data as a CSV file download.
 * @param headers - Column header names
 * @param rows - 2D array of cell values
 * @param filename - Name for the downloaded file (defaults to "export.csv")
 */
export function exportCSV(
  headers: string[],
  rows: unknown[][],
  filename: string = 'export.csv'
): void {
  const csvContent = buildCSVString(headers, rows);
  const BOM = '\uFEFF';
  const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();

  // Clean up
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
