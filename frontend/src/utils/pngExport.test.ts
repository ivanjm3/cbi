import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { exportPNG } from './pngExport';

// Mock html2canvas
vi.mock('html2canvas', () => ({
  default: vi.fn(),
}));

import html2canvas from 'html2canvas';

describe('exportPNG', () => {
  let mockElement: HTMLElement;
  let mockCanvas: HTMLCanvasElement;
  let mockLink: HTMLAnchorElement;
  let createObjectURLMock: ReturnType<typeof vi.fn>;
  let revokeObjectURLMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();

    // Create a mock element with dimensions
    mockElement = document.createElement('div');
    Object.defineProperty(mockElement, 'offsetWidth', { value: 800 });
    Object.defineProperty(mockElement, 'offsetHeight', { value: 600 });

    // Create a mock canvas that returns a blob
    mockCanvas = document.createElement('canvas');
    const mockBlob = new Blob(['fake-png-data'], { type: 'image/png' });
    vi.spyOn(mockCanvas, 'toBlob').mockImplementation((callback) => {
      callback(mockBlob);
    });

    // Mock html2canvas to return our mock canvas
    vi.mocked(html2canvas).mockResolvedValue(mockCanvas);

    // Mock URL.createObjectURL and revokeObjectURL
    createObjectURLMock = vi.fn().mockReturnValue('blob:http://localhost/fake-url');
    revokeObjectURLMock = vi.fn();
    URL.createObjectURL = createObjectURLMock;
    URL.revokeObjectURL = revokeObjectURLMock;

    // Spy on link click and DOM operations
    mockLink = document.createElement('a');
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') return mockLink;
      return document.createElement(tag);
    });
    vi.spyOn(mockLink, 'click').mockImplementation(() => {});
    vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node as HTMLElement);
    vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node as HTMLElement);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('captures the element using html2canvas with correct dimensions', async () => {
    await exportPNG({ element: mockElement });

    expect(html2canvas).toHaveBeenCalledWith(mockElement, {
      useCORS: true,
      backgroundColor: '#ffffff',
      width: 800,
      height: 600,
    });
  });

  it('triggers a download with the correct filename', async () => {
    await exportPNG({ element: mockElement, filename: 'my-chart' });

    expect(mockLink.download).toBe('my-chart.png');
    expect(mockLink.href).toBe('blob:http://localhost/fake-url');
    expect(mockLink.click).toHaveBeenCalled();
  });

  it('uses default filename when none provided', async () => {
    await exportPNG({ element: mockElement });

    expect(mockLink.download).toBe('chart-export.png');
  });

  it('creates and revokes the object URL', async () => {
    await exportPNG({ element: mockElement });

    expect(createObjectURLMock).toHaveBeenCalled();

    // Advance timers to trigger cleanup
    vi.advanceTimersByTime(100);
    expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:http://localhost/fake-url');
  });

  it('cleans up the link element from DOM after click', async () => {
    await exportPNG({ element: mockElement });

    expect(document.body.appendChild).toHaveBeenCalledWith(mockLink);
    expect(document.body.removeChild).toHaveBeenCalledWith(mockLink);
  });

  it('calls onError callback when html2canvas fails', async () => {
    const error = new Error('Canvas rendering failed');
    vi.mocked(html2canvas).mockRejectedValue(error);
    const onError = vi.fn();

    await exportPNG({ element: mockElement, onError });

    expect(onError).toHaveBeenCalledWith(error);
  });

  it('calls onError callback when toBlob returns null', async () => {
    vi.spyOn(mockCanvas, 'toBlob').mockImplementation((callback) => {
      callback(null);
    });
    const onError = vi.fn();

    await exportPNG({ element: mockElement, onError });

    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'Failed to convert canvas to PNG blob' })
    );
  });

  it('logs error to console when no onError callback provided', async () => {
    const error = new Error('Canvas rendering failed');
    vi.mocked(html2canvas).mockRejectedValue(error);
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await exportPNG({ element: mockElement });

    expect(consoleSpy).toHaveBeenCalledWith('PNG export failed:', error);
  });

  it('wraps non-Error thrown values into Error objects for onError', async () => {
    vi.mocked(html2canvas).mockRejectedValue('string error');
    const onError = vi.fn();

    await exportPNG({ element: mockElement, onError });

    expect(onError).toHaveBeenCalledWith(expect.any(Error));
    expect(onError.mock.calls[0][0].message).toBe('string error');
  });
});
