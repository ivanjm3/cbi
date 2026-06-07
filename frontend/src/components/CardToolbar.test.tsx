import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import CardToolbar from './CardToolbar';
import { useSessionStore } from '../store/sessionStore';
import type { RenderedOutput } from '../types';

// Mock the sessionStore
vi.mock('../store/sessionStore', () => ({
  useSessionStore: vi.fn(),
}));

// Mock exportPNG
vi.mock('../utils/pngExport', () => ({
  exportPNG: vi.fn(),
}));

// Mock exportCSV
vi.mock('../utils/csvExport', () => ({
  exportCSV: vi.fn(),
}));

import { exportPNG } from '../utils/pngExport';
import { exportCSV } from '../utils/csvExport';

const mockExportPNG = vi.mocked(exportPNG);
const mockExportCSV = vi.mocked(exportCSV);
const mockUseSessionStore = vi.mocked(useSessionStore);

function createMockChartData(overrides?: Partial<RenderedOutput>): RenderedOutput {
  return {
    output_type: 'chart',
    chart_type: 'bar',
    chart_data: {
      labels: ['Q1', 'Q2', 'Q3'],
      datasets: [{ label: 'Revenue', data: [100, 200, 300] }],
    },
    text_content: null,
    description: 'Test chart',
    metadata: {
      query_id: 'test-id',
      query_type: 'aggregation',
    },
    ...overrides,
  };
}

describe('CardToolbar', () => {
  let mockPinCard: ReturnType<typeof vi.fn>;
  let mockUnpinCard: ReturnType<typeof vi.fn>;
  let mockSaveBookmark: ReturnType<typeof vi.fn>;
  let mockOnExpandFullscreen: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockPinCard = vi.fn();
    mockUnpinCard = vi.fn();
    mockSaveBookmark = vi.fn();
    mockOnExpandFullscreen = vi.fn();

    mockUseSessionStore.mockImplementation((selector: unknown) => {
      const state = {
        pinCard: mockPinCard,
        unpinCard: mockUnpinCard,
        saveBookmark: mockSaveBookmark,
      };
      return (selector as (s: typeof state) => unknown)(state);
    });

    mockExportPNG.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function renderToolbar(props?: Partial<Parameters<typeof CardToolbar>[0]>) {
    const el = document.createElement('div');
    const cardRef = { current: el };
    const defaultProps = {
      cardId: 'card-123',
      cardRef,
      chartData: createMockChartData(),
      pinned: false,
      onExpandFullscreen: mockOnExpandFullscreen,
    };
    return render(<CardToolbar {...defaultProps} {...props} />);
  }

  it('renders all toolbar buttons', () => {
    renderToolbar();

    expect(screen.getByLabelText('Download PNG')).toBeInTheDocument();
    expect(screen.getByLabelText('Download CSV')).toBeInTheDocument();
    expect(screen.getByLabelText('Pin card')).toBeInTheDocument();
    expect(screen.getByLabelText('Expand fullscreen')).toBeInTheDocument();
    expect(screen.getByLabelText('Bookmark')).toBeInTheDocument();
    expect(screen.getByTestId('drag-handle')).toBeInTheDocument();
  });

  it('calls exportPNG with correct arguments on Download PNG click', async () => {
    const user = userEvent.setup();
    const el = document.createElement('div');
    const cardRef = { current: el };
    renderToolbar({ cardRef, cardId: 'my-card' });

    await user.click(screen.getByLabelText('Download PNG'));

    expect(mockExportPNG).toHaveBeenCalledWith(
      el,
      'chart-my-card.png',
      expect.any(Function),
    );
  });

  it('shows error message when PNG export fails', async () => {
    const user = userEvent.setup();
    mockExportPNG.mockImplementation(async (_el, _filename, onError) => {
      if (onError) onError(new Error('fail'));
    });
    renderToolbar();

    await user.click(screen.getByLabelText('Download PNG'));

    await waitFor(() => {
      expect(screen.getByTestId('export-error')).toHaveTextContent('Export failed');
    });
  });

  it('shows error when cardRef is null on PNG export', async () => {
    const user = userEvent.setup();
    const cardRef = { current: null };
    renderToolbar({ cardRef });

    await user.click(screen.getByLabelText('Download PNG'));

    await waitFor(() => {
      expect(screen.getByTestId('export-error')).toHaveTextContent('Export failed');
    });
  });

  it('calls exportCSV with extracted data on Download CSV click', async () => {
    const user = userEvent.setup();
    renderToolbar();

    await user.click(screen.getByLabelText('Download CSV'));

    expect(mockExportCSV).toHaveBeenCalledWith(
      ['Label', 'Revenue'],
      [['Q1', 100], ['Q2', 200], ['Q3', 300]],
      'data-card-123.csv',
    );
  });

  it('shows error when chart_data is null on CSV export', async () => {
    const user = userEvent.setup();
    renderToolbar({ chartData: createMockChartData({ chart_data: null }) });

    await user.click(screen.getByLabelText('Download CSV'));

    await waitFor(() => {
      expect(screen.getByTestId('export-error')).toHaveTextContent('Export failed');
    });
  });

  it('calls pinCard when unpinned card is pinned', async () => {
    const user = userEvent.setup();
    renderToolbar({ pinned: false, cardId: 'abc' });

    await user.click(screen.getByLabelText('Pin card'));

    expect(mockPinCard).toHaveBeenCalledWith('abc');
  });

  it('calls unpinCard when pinned card is unpinned', async () => {
    const user = userEvent.setup();
    renderToolbar({ pinned: true, cardId: 'abc' });

    await user.click(screen.getByLabelText('Unpin card'));

    expect(mockUnpinCard).toHaveBeenCalledWith('abc');
  });

  it('displays visual pinned-state indicator when pinned', () => {
    renderToolbar({ pinned: true });

    const pinBtn = screen.getByLabelText('Unpin card');
    expect(pinBtn).toHaveClass('text-blue-600', 'bg-blue-100');
    expect(pinBtn).toHaveAttribute('aria-pressed', 'true');
  });

  it('calls onExpandFullscreen on Expand button click', async () => {
    const user = userEvent.setup();
    renderToolbar();

    await user.click(screen.getByLabelText('Expand fullscreen'));

    expect(mockOnExpandFullscreen).toHaveBeenCalled();
  });

  it('calls saveBookmark on Bookmark button click', async () => {
    const user = userEvent.setup();
    renderToolbar({ cardId: 'card-xyz-456-789' });

    await user.click(screen.getByLabelText('Bookmark'));

    expect(mockSaveBookmark).toHaveBeenCalledWith('Card card-xyz');
  });

  it('supports columns/rows format for CSV export', async () => {
    const user = userEvent.setup();
    const chartData = createMockChartData({
      chart_data: {
        columns: ['Name', 'Age'],
        rows: [['Alice', 30], ['Bob', 25]],
      },
    });
    renderToolbar({ chartData });

    await user.click(screen.getByLabelText('Download CSV'));

    expect(mockExportCSV).toHaveBeenCalledWith(
      ['Name', 'Age'],
      [['Alice', 30], ['Bob', 25]],
      'data-card-123.csv',
    );
  });
});
