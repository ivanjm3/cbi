import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { escapeCSVField, buildCSVString, exportCSV } from './csvExport';

describe('escapeCSVField', () => {
  it('returns plain field unchanged', () => {
    expect(escapeCSVField('hello')).toBe('hello');
  });

  it('returns empty string unchanged', () => {
    expect(escapeCSVField('')).toBe('');
  });

  it('wraps field containing comma in double quotes', () => {
    expect(escapeCSVField('a,b')).toBe('"a,b"');
  });

  it('wraps field containing newline in double quotes', () => {
    expect(escapeCSVField('line1\nline2')).toBe('"line1\nline2"');
  });

  it('wraps field containing carriage return in double quotes', () => {
    expect(escapeCSVField('line1\rline2')).toBe('"line1\rline2"');
  });

  it('doubles internal double quotes and wraps in quotes', () => {
    expect(escapeCSVField('say "hello"')).toBe('"say ""hello"""');
  });

  it('handles field with comma and quotes together', () => {
    expect(escapeCSVField('"price",100')).toBe('"""price"",100"');
  });
});

describe('buildCSVString', () => {
  it('produces headers as first row', () => {
    const csv = buildCSVString(['Name', 'Age'], []);
    expect(csv).toBe('Name,Age');
  });

  it('produces headers followed by data rows separated by CRLF', () => {
    const csv = buildCSVString(['A', 'B'], [['1', '2'], ['3', '4']]);
    expect(csv).toBe('A,B\r\n1,2\r\n3,4');
  });

  it('escapes special characters in headers and cells', () => {
    const csv = buildCSVString(['Col, 1', 'Col "2"'], [['val\nue', 'normal']]);
    expect(csv).toBe('"Col, 1","Col ""2"""\r\n"val\nue",normal');
  });

  it('handles single column with no rows', () => {
    const csv = buildCSVString(['Only'], []);
    expect(csv).toBe('Only');
  });

  it('handles empty headers and empty rows', () => {
    const csv = buildCSVString([], [[]]);
    expect(csv).toBe('\r\n');
  });
});

describe('exportCSV', () => {
  let createObjectURLMock: ReturnType<typeof vi.fn>;
  let revokeObjectURLMock: ReturnType<typeof vi.fn>;
  let appendChildSpy: ReturnType<typeof vi.spyOn>;
  let removeChildSpy: ReturnType<typeof vi.spyOn>;
  let clickMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    createObjectURLMock = vi.fn().mockReturnValue('blob:test-url');
    revokeObjectURLMock = vi.fn();
    clickMock = vi.fn();

    globalThis.URL.createObjectURL = createObjectURLMock;
    globalThis.URL.revokeObjectURL = revokeObjectURLMock;

    appendChildSpy = vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
    removeChildSpy = vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);

    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        return {
          href: '',
          download: '',
          style: { display: '' },
          click: clickMock,
        } as unknown as HTMLAnchorElement;
      }
      return document.createElement(tag);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('creates a Blob with CSV content and UTF-8 encoding', () => {
    exportCSV(['H1'], [['v1']], 'test.csv');

    expect(createObjectURLMock).toHaveBeenCalledTimes(1);
    const blobArg = createObjectURLMock.mock.calls[0][0];
    expect(blobArg).toBeInstanceOf(Blob);
    expect(blobArg.type).toBe('text/csv;charset=utf-8;');
  });

  it('triggers a download by clicking the link', () => {
    exportCSV(['Col'], [['data']], 'out.csv');
    expect(clickMock).toHaveBeenCalledTimes(1);
  });

  it('appends and removes the link element from the DOM', () => {
    exportCSV(['Col'], [['data']]);
    expect(appendChildSpy).toHaveBeenCalledTimes(1);
    expect(removeChildSpy).toHaveBeenCalledTimes(1);
  });

  it('revokes the object URL after download', () => {
    exportCSV(['Col'], [['data']]);
    expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:test-url');
  });

  it('uses default filename when none provided', () => {
    exportCSV(['Col'], [['data']]);
    const linkEl = appendChildSpy.mock.calls[0][0] as unknown as { download: string };
    expect(linkEl.download).toBe('export.csv');
  });

  it('uses custom filename when provided', () => {
    exportCSV(['Col'], [['data']], 'my-report.csv');
    const linkEl = appendChildSpy.mock.calls[0][0] as unknown as { download: string };
    expect(linkEl.download).toBe('my-report.csv');
  });
});
