import html2canvas from 'html2canvas';

export interface ExportPNGOptions {
  /** The HTML element to capture (typically the chart container). */
  element: HTMLElement;
  /** The filename for the downloaded PNG (without extension). */
  filename?: string;
  /** Optional callback invoked if the export fails. */
  onError?: (error: Error) => void;
}

/**
 * Exports an HTML element as a PNG image file.
 *
 * Uses html2canvas to render the element to a canvas at its current
 * rendered pixel dimensions, converts it to a PNG blob, and triggers
 * a browser download. Cleans up the object URL after download.
 *
 * @param options - Configuration for the export operation
 */
export async function exportPNG(options: ExportPNGOptions): Promise<void> {
  const { element, filename = 'chart-export', onError } = options;

  try {
    const canvas = await html2canvas(element, {
      useCORS: true,
      backgroundColor: '#ffffff',
      width: element.offsetWidth,
      height: element.offsetHeight,
    });

    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((b) => {
        if (b) {
          resolve(b);
        } else {
          reject(new Error('Failed to convert canvas to PNG blob'));
        }
      }, 'image/png');
    });

    const url = URL.createObjectURL(blob);

    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // Clean up the object URL after a short delay to ensure download starts
    setTimeout(() => URL.revokeObjectURL(url), 100);
  } catch (err) {
    const error = err instanceof Error ? err : new Error(String(err));
    if (onError) {
      onError(error);
    } else {
      console.error('PNG export failed:', error);
    }
  }
}
