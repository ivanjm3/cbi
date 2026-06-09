/**
 * Unit tests for FooterBar component.
 * Validates: Requirements 1.6, 3.1, 3.3
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FooterBar } from './FooterBar';
import { useSessionStore } from '../store/sessionStore';

describe('FooterBar', () => {
  beforeEach(() => {
    useSessionStore.setState({
      traceabilityPanelVisible: false,
      sidebarCollapsed: false,
      savedPrompts: [],
      chatHistory: [],
      chatThread: [],
      cards: {},
      activeCardId: null,
      loading: false,
      statsPanelCollapsed: false,
    });
  });

  it('renders the "Trace" label (Requirement 1.6)', () => {
    render(<FooterBar />);
    expect(
      screen.getByText('Trace'),
    ).toBeInTheDocument();
  });

  it('renders as a clickable button element (Requirement 1.6)', () => {
    render(<FooterBar />);
    const button = screen.getByRole('button', {
      name: /toggle traceability panel/i,
    });
    expect(button).toBeInTheDocument();
  });

  it('toggles traceability panel visibility on click (Requirement 3.1)', async () => {
    const user = userEvent.setup();
    render(<FooterBar />);

    expect(useSessionStore.getState().traceabilityPanelVisible).toBe(false);

    const button = screen.getByRole('button', {
      name: /toggle traceability panel/i,
    });
    await user.click(button);

    expect(useSessionStore.getState().traceabilityPanelVisible).toBe(true);
  });

  it('hides the panel when clicked while panel is visible (Requirement 3.3)', async () => {
    const user = userEvent.setup();
    useSessionStore.setState({ traceabilityPanelVisible: true });

    render(<FooterBar />);

    const button = screen.getByRole('button', {
      name: /toggle traceability panel/i,
    });
    await user.click(button);

    expect(useSessionStore.getState().traceabilityPanelVisible).toBe(false);
  });

  it('reflects pressed state via aria-pressed when panel is visible', () => {
    useSessionStore.setState({ traceabilityPanelVisible: true });
    render(<FooterBar />);

    const button = screen.getByRole('button', {
      name: /toggle traceability panel/i,
    });
    expect(button).toHaveAttribute('aria-pressed', 'true');
  });

  it('reflects unpressed state via aria-pressed when panel is hidden', () => {
    render(<FooterBar />);

    const button = screen.getByRole('button', {
      name: /toggle traceability panel/i,
    });
    expect(button).toHaveAttribute('aria-pressed', 'false');
  });
});
