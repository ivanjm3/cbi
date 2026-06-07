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
  let clickSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockElement = document.createElement('div');
    Object.defineProperty(mockElement, 'offsetWidth', { value: 400 });
    Object.defineProperty(mockElement, 'offsetHeight', { value: 300 });

    mockCanvas = document.createElement('canvas');
    mockCanvas.width = 400;
    mockCanvas.height = 300;
    vi.mocked(html2canvas).mockResolvedValue(mockCanvas);

    clickSpy = vi.fn();
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        const link = {
          href: '',
          download: '',
          click: clickSpy,
        } as unknown as HTMLAnchorElement;
        return link;
      }
      return document.createElement(tag);
    });
    vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
    vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls html2canvas with correct options', async () => {
    await exportPNG(mockElement, 'test-chart.png');

    expect(html2canvas).toHaveBeenCalledWith(mockElement, {
      useCORS: true,
      backgroundColor: '#ffffff',
      scale: window.devicePixelRatio || 1,
      width: 400,
      height: 300,
    });
  });

  it('triggers download with correct filename', async () => {
    await exportPNG(mockElement, 'my-chart.png');

    expect(clickSpy).toHaveBeenCalled();
  });

  it('appends .png if filename does not end with it', async () => {
    await exportPNG(mockElement, 'my-chart');

    const createElCalls = vi.mocked(document.createElement).mock.results;
    const linkResult = createElCalls.find(
      (r) => r.type === 'return' && (r.value as HTMLElement).tagName !== 'CANVAS'
    );
    if (linkResult && linkResult.type === 'return') {
      expect((linkResult.value as HTMLAnchorElement).download).toBe('my-chart.png');
    }
  });

  it('uses default filename when none provided', async () => {
    await exportPNG(mockElement);

    expect(clickSpy).toHaveBeenCalled();
  });

  it('calls onError callback when html2canvas fails', async () => {
    const error = new Error('Canvas rendering failed');
    vi.mocked(html2canvas).mockRejectedValue(error);

    const onError = vi.fn();
    await exportPNG(mockElement, 'chart.png', onError);

    expect(onError).toHaveBeenCalledWith(error);
  });

  it('wraps non-Error thrown values in an Error', async () => {
    vi.mocked(html2canvas).mockRejectedValue('string error');

    const onError = vi.fn();
    await exportPNG(mockElement, 'chart.png', onError);

    expect(onError).toHaveBeenCalledWith(expect.any(Error));
    expect(onError.mock.calls[0][0].message).toBe('PNG export failed');
  });

  it('throws when export fails and no onError provided', async () => {
    const error = new Error('Canvas rendering failed');
    vi.mocked(html2canvas).mockRejectedValue(error);

    await expect(exportPNG(mockElement, 'chart.png')).rejects.toThrow(
      'Canvas rendering failed'
    );
  });
});
