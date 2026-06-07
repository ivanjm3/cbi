import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { escapeCSVField, buildCSVString, exportCSV } from './csvExport';

describe('escapeCSVField', () => {
  it('returns empty string for null/undefined', () => {
    expect(escapeCSVField(null)).toBe('');
    expect(escapeCSVField(undefined)).toBe('');
  });

  it('converts numbers to strings', () => {
    expect(escapeCSVField(42)).toBe('42');
    expect(escapeCSVField(3.14)).toBe('3.14');
  });

  it('passes through plain strings unchanged', () => {
    expect(escapeCSVField('hello')).toBe('hello');
    expect(escapeCSVField('simple value')).toBe('simple value');
  });

  it('wraps values containing commas in double quotes', () => {
    expect(escapeCSVField('one,two')).toBe('"one,two"');
  });

  it('wraps values containing double quotes and escapes them by doubling', () => {
    expect(escapeCSVField('say "hello"')).toBe('"say ""hello"""');
  });

  it('wraps values containing newlines in double quotes', () => {
    expect(escapeCSVField('line1\nline2')).toBe('"line1\nline2"');
    expect(escapeCSVField('line1\r\nline2')).toBe('"line1\r\nline2"');
  });

  it('handles values with multiple special characters', () => {
    expect(escapeCSVField('a,"b"\nc')).toBe('"a,""b""\nc"');
  });
});

describe('buildCSVString', () => {
  it('produces header row followed by data rows with CRLF', () => {
    const headers = ['Name', 'Age'];
    const rows = [['Alice', 30], ['Bob', 25]];
    const result = buildCSVString(headers, rows);
    expect(result).toBe('Name,Age\r\nAlice,30\r\nBob,25');
  });

  it('handles empty rows array', () => {
    const headers = ['Col1', 'Col2'];
    const rows: unknown[][] = [];
    const result = buildCSVString(headers, rows);
    expect(result).toBe('Col1,Col2');
  });

  it('escapes special characters in headers and cells', () => {
    const headers = ['Name, First', 'Quote "Value"'];
    const rows = [['hello\nworld', 'normal']];
    const result = buildCSVString(headers, rows);
    expect(result).toBe('"Name, First","Quote ""Value"""\r\n"hello\nworld",normal');
  });

  it('handles null/undefined values in data rows', () => {
    const headers = ['A', 'B'];
    const rows = [[null, undefined]];
    const result = buildCSVString(headers, rows);
    expect(result).toBe('A,B\r\n,');
  });
});

describe('exportCSV', () => {
  let createElementSpy: ReturnType<typeof vi.spyOn>;
  let createObjectURLSpy: ReturnType<typeof vi.spyOn>;
  let revokeObjectURLSpy: ReturnType<typeof vi.spyOn>;
  let appendChildSpy: ReturnType<typeof vi.spyOn>;
  let removeChildSpy: ReturnType<typeof vi.spyOn>;
  let mockLink: { href: string; download: string; style: { display: string }; click: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    mockLink = {
      href: '',
      download: '',
      style: { display: '' },
      click: vi.fn(),
    };

    createElementSpy = vi.spyOn(document, 'createElement').mockReturnValue(mockLink as unknown as HTMLElement);
    createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-url');
    revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    appendChildSpy = vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
    removeChildSpy = vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('creates a link element and triggers download', () => {
    exportCSV(['Name'], [['Alice']], 'test.csv');

    expect(createElementSpy).toHaveBeenCalledWith('a');
    expect(createObjectURLSpy).toHaveBeenCalled();
    expect(mockLink.href).toBe('blob:mock-url');
    expect(mockLink.download).toBe('test.csv');
    expect(mockLink.style.display).toBe('none');
    expect(appendChildSpy).toHaveBeenCalled();
    expect(mockLink.click).toHaveBeenCalled();
    expect(removeChildSpy).toHaveBeenCalled();
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:mock-url');
  });

  it('uses default filename when not provided', () => {
    exportCSV(['A'], [['1']]);
    expect(mockLink.download).toBe('export.csv');
  });

  it('creates a Blob with UTF-8 BOM and CSV content', () => {
    exportCSV(['Col'], [['val']]);

    const blobArg = (createObjectURLSpy.mock.calls[0] as unknown[])[0] as Blob;
    expect(blobArg).toBeInstanceOf(Blob);
    expect(blobArg.type).toBe('text/csv;charset=utf-8;');
  });
});
