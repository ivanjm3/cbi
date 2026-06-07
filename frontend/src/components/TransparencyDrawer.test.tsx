import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import { TransparencyDrawer } from './TransparencyDrawer';
import type { MetaPayload } from '../types';

const fullMetadata: MetaPayload = {
  query_id: 'abc-123',
  query_type: 'aggregation',
  timestamp: '2025-01-15T10:30:00Z',
  data_sources: ['financial_data', 'product_catalog'],
};

describe('TransparencyDrawer', () => {
  it('renders collapsed by default', () => {
    render(<TransparencyDrawer description="Test" metadata={fullMetadata} />);
    const toggle = screen.getByRole('button', { name: /how i got this/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Query Rewrite')).not.toBeInTheDocument();
  });

  it('expands when toggle is clicked', async () => {
    const user = userEvent.setup();
    render(<TransparencyDrawer description="Revenue by region" metadata={fullMetadata} />);

    const toggle = screen.getByRole('button', { name: /how i got this/i });
    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Query Rewrite')).toBeInTheDocument();
    expect(screen.getByText('Revenue by region')).toBeInTheDocument();
  });

  it('collapses when toggle is clicked again', async () => {
    const user = userEvent.setup();
    render(<TransparencyDrawer description="Test" metadata={fullMetadata} />);

    const toggle = screen.getByRole('button', { name: /how i got this/i });
    await user.click(toggle); // expand
    await user.click(toggle); // collapse

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Query Rewrite')).not.toBeInTheDocument();
  });

  it('displays all three sections with full data', async () => {
    const user = userEvent.setup();
    render(<TransparencyDrawer description="Revenue breakdown" metadata={fullMetadata} />);

    await user.click(screen.getByRole('button', { name: /how i got this/i }));

    // Section 1: Query Rewrite
    expect(screen.getByText('Revenue breakdown')).toBeInTheDocument();

    // Section 2: Structured Intent JSON
    expect(screen.getByText(/abc-123/)).toBeInTheDocument();
    expect(screen.getByText(/aggregation/)).toBeInTheDocument();
    expect(screen.getByText(/2025-01-15T10:30:00Z/)).toBeInTheDocument();

    // Section 3: API Call Summary
    expect(screen.getByText('financial_data')).toBeInTheDocument();
    expect(screen.getByText('product_catalog')).toBeInTheDocument();
  });

  it('shows placeholder for missing description', async () => {
    const user = userEvent.setup();
    render(<TransparencyDrawer description={null} metadata={fullMetadata} />);

    await user.click(screen.getByRole('button', { name: /how i got this/i }));

    const placeholders = screen.getAllByText('Data not available');
    expect(placeholders.length).toBeGreaterThanOrEqual(1);
  });

  it('shows placeholder for missing metadata', async () => {
    const user = userEvent.setup();
    render(<TransparencyDrawer description="Test" metadata={null} />);

    await user.click(screen.getByRole('button', { name: /how i got this/i }));

    // Both structured intent and API call summary should show placeholder
    const placeholders = screen.getAllByText('Data not available');
    expect(placeholders.length).toBe(2);
  });

  it('shows placeholder for empty data_sources', async () => {
    const user = userEvent.setup();
    const metadata: MetaPayload = {
      query_id: 'abc-123',
      query_type: 'aggregation',
      data_sources: [],
    };
    render(<TransparencyDrawer description="Test" metadata={metadata} />);

    await user.click(screen.getByRole('button', { name: /how i got this/i }));

    // API call summary placeholder
    const section = screen.getByText('API Call Summary').parentElement;
    expect(section?.querySelector('.italic')).toHaveTextContent('Data not available');
  });

  it('shows all placeholders when no props provided', async () => {
    const user = userEvent.setup();
    render(<TransparencyDrawer />);

    await user.click(screen.getByRole('button', { name: /how i got this/i }));

    const placeholders = screen.getAllByText('Data not available');
    expect(placeholders.length).toBe(3);
  });
});
