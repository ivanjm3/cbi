import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import VisualizationCard from './VisualizationCard';
import { useSessionStore } from '../store/sessionStore';
import type { CardState } from '../types';

// Mock the sessionStore
vi.mock('../store/sessionStore', () => ({
  useSessionStore: vi.fn(),
}));

// Mock exports so CardToolbar doesn't try to call real export functions
vi.mock('../utils/pngExport', () => ({
  exportPNG: vi.fn(),
}));

vi.mock('../utils/csvExport', () => ({
  exportCSV: vi.fn(),
}));

const mockUseSessionStore = vi.mocked(useSessionStore);

function createMockCard(overrides?: Partial<CardState>): CardState {
  return {
    id: 'card-1',
    query: 'show revenue by region',
    renderedOutput: {
      output_type: 'chart',
      chart_type: 'bar',
      chart_data: { labels: ['A', 'B'], datasets: [{ label: 'Revenue', data: [10, 20] }] },
      description: 'Revenue by region',
      metadata: {
        query_id: 'q-123',
        query_type: 'aggregation',
        latency_ms: 250,
        row_count: 8,
        columns: [],
      },
    },
    gridPosition: { col: 0, row: 0 },
    gridSize: { colSpan: 1, rowSpan: 1 },
    pinned: false,
    createdAt: Date.now(),
    ...overrides,
  };
}

describe('VisualizationCard', () => {
  let mockSetActiveCard: ReturnType<typeof vi.fn>;
  let mockPinCard: ReturnType<typeof vi.fn>;
  let mockUnpinCard: ReturnType<typeof vi.fn>;
  let mockSaveBookmark: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockSetActiveCard = vi.fn();
    mockPinCard = vi.fn();
    mockUnpinCard = vi.fn();
    mockSaveBookmark = vi.fn();
    mockUseSessionStore.mockImplementation((selector: unknown) => {
      const state = {
        setActiveCard: mockSetActiveCard,
        activeCardId: null,
        pinCard: mockPinCard,
        unpinCard: mockUnpinCard,
        saveBookmark: mockSaveBookmark,
      };
      return (selector as (s: typeof state) => unknown)(state);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the user query text at the top', () => {
    const card = createMockCard();
    render(<VisualizationCard card={card} />);

    const userMessage = screen.getByTestId('user-message');
    expect(userMessage).toHaveTextContent('show revenue by region');
  });

  it('renders ChartRenderer with chart content', () => {
    const card = createMockCard();
    render(<VisualizationCard card={card} />);

    // ChartRenderer renders with a data-testid based on chart type
    expect(screen.getByTestId('chart-bar')).toBeInTheDocument();
  });

  it('renders CardToolbar with card actions', () => {
    const card = createMockCard();
    render(<VisualizationCard card={card} />);

    expect(screen.getByTestId('card-toolbar')).toBeInTheDocument();
  });

  it('renders TransparencyDrawer with "How I got this" toggle', () => {
    const card = createMockCard();
    render(<VisualizationCard card={card} />);

    expect(screen.getByText('How I got this')).toBeInTheDocument();
  });

  it('calls setActiveCard on click', async () => {
    const user = userEvent.setup();
    const card = createMockCard({ id: 'card-42' });
    render(<VisualizationCard card={card} />);

    const cardEl = screen.getByTestId('visualization-card-card-42');
    await user.click(cardEl);

    expect(mockSetActiveCard).toHaveBeenCalledWith('card-42');
  });

  it('calls setActiveCard on focus', () => {
    const card = createMockCard({ id: 'card-99' });
    render(<VisualizationCard card={card} />);

    const cardEl = screen.getByTestId('visualization-card-card-99');
    cardEl.focus();

    expect(mockSetActiveCard).toHaveBeenCalledWith('card-99');
  });

  it('shows active styling when card is the active card', () => {
    mockUseSessionStore.mockImplementation((selector: unknown) => {
      const state = {
        setActiveCard: mockSetActiveCard,
        activeCardId: 'card-1',
        pinCard: mockPinCard,
        unpinCard: mockUnpinCard,
        saveBookmark: mockSaveBookmark,
      };
      return (selector as (s: typeof state) => unknown)(state);
    });

    const card = createMockCard({ id: 'card-1' });
    render(<VisualizationCard card={card} />);

    const cardEl = screen.getByTestId('visualization-card-card-1');
    expect(cardEl).toHaveClass('border-blue-500');
  });

  it('shows inactive styling when card is not active', () => {
    const card = createMockCard({ id: 'card-1' });
    render(<VisualizationCard card={card} />);

    const cardEl = screen.getByTestId('visualization-card-card-1');
    expect(cardEl).toHaveClass('border-gray-200');
  });

  it('has accessible article role and label', () => {
    const card = createMockCard({ query: 'total sales Q4' });
    render(<VisualizationCard card={card} />);

    const article = screen.getByRole('article', {
      name: 'Visualization for: total sales Q4',
    });
    expect(article).toBeInTheDocument();
  });

  it('is focusable via tabIndex', () => {
    const card = createMockCard();
    render(<VisualizationCard card={card} />);

    const cardEl = screen.getByTestId('visualization-card-card-1');
    expect(cardEl).toHaveAttribute('tabindex', '0');
  });
});
