import html2canvas from 'html2canvas';

/**
 * Export a DOM element as a PNG image and trigger a file download.
 *
 * Uses html2canvas to rasterize the target element at its rendered dimensions.
 * On failure, invokes the optional `onError` callback instead of throwing.
 *
 * @param element - The DOM element to capture (typically the chart card container)
 * @param filename - The download filename (defaults to "chart.png")
 * @param onError - Optional callback invoked with the error when export fails
 */
export async function exportPNG(
  element: HTMLElement,
  filename: string = 'chart.png',
  onError?: (error: Error) => void
): Promise<void> {
  try {
    const canvas = await html2canvas(element, {
      useCORS: true,
      backgroundColor: '#ffffff',
      scale: window.devicePixelRatio || 1,
      width: element.offsetWidth,
      height: element.offsetHeight,
    });

    const dataUrl = canvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.href = dataUrl;
    link.download = filename.endsWith('.png') ? filename : `${filename}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } catch (err) {
    const error =
      err instanceof Error ? err : new Error('PNG export failed');
    if (onError) {
      onError(error);
    } else {
      throw error;
    }
  }
}
