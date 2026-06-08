/**
 * CSV export utility for downloading chart data.
 *
 * Generates RFC 4180-compliant CSV and triggers a browser download
 * via Blob + object URL.
 */

/**
 * Escape a single cell value per RFC 4180.
 * Fields containing commas, double quotes, or newlines are enclosed
 * in double quotes. Any double quotes within the field are doubled.
 */
export function escapeCSVField(field: string): string {
  if (field.includes('"') || field.includes(',') || field.includes('\n') || field.includes('\r')) {
    return `"${field.replace(/"/g, '""')}"`;
  }
  return field;
}

/**
 * Build a CSV string from headers and rows.
 * Headers appear as the first row, followed by data rows.
 * Each row is terminated with CRLF per RFC 4180.
 */
export function buildCSVString(headers: string[], rows: string[][]): string {
  const lines: string[] = [];
  lines.push(headers.map(escapeCSVField).join(','));
  for (const row of rows) {
    lines.push(row.map(escapeCSVField).join(','));
  }
  return lines.join('\r\n');
}

/**
 * Export data as a CSV file download.
 *
 * @param headers - Column header names
 * @param rows - 2D array of cell values
 * @param filename - Output filename (defaults to "export.csv")
 */
export function exportCSV(
  headers: string[],
  rows: string[][],
  filename: string = 'export.csv',
): void {
  const csvContent = buildCSVString(headers, rows);
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  URL.revokeObjectURL(url);
}
