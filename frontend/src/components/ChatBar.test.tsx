import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ChatBar } from './ChatBar';
import { useSessionStore } from '../store/sessionStore';

// Mock the sessionStore
vi.mock('../store/sessionStore', () => ({
  useSessionStore: vi.fn(),
}));

const mockUseSessionStore = vi.mocked(useSessionStore);

describe('ChatBar', () => {
  let mockSubmitQuery: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockSubmitQuery = vi.fn().mockResolvedValue(undefined);
    mockUseSessionStore.mockImplementation((selector: unknown) => {
      const state = {
        loading: false,
        submitQuery: mockSubmitQuery,
      };
      return (selector as (s: typeof state) => unknown)(state);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders input, submit button, and voice icon when Speech API is supported', () => {
    // Mock SpeechRecognition support
    Object.defineProperty(window, 'webkitSpeechRecognition', {
      value: class {},
      writable: true,
      configurable: true,
    });

    render(<ChatBar />);

    expect(screen.getByLabelText('Query input')).toBeInTheDocument();
    expect(screen.getByLabelText('Submit query')).toBeInTheDocument();
    expect(screen.getByLabelText('Voice input')).toBeInTheDocument();

    // Clean up
    delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
  });

  it('hides voice icon when Speech API is not supported', () => {
    // Ensure no Speech API
    delete (window as unknown as Record<string, unknown>).SpeechRecognition;
    delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;

    render(<ChatBar />);

    expect(screen.queryByLabelText('Voice input')).not.toBeInTheDocument();
  });

  it('prevents submission when input is empty', async () => {
    const user = userEvent.setup();
    render(<ChatBar />);

    const submitBtn = screen.getByLabelText('Submit query');
    expect(submitBtn).toBeDisabled();

    await user.click(submitBtn);
    expect(mockSubmitQuery).not.toHaveBeenCalled();
  });

  it('prevents submission when input contains only whitespace', async () => {
    const user = userEvent.setup();
    render(<ChatBar />);

    const input = screen.getByLabelText('Query input');
    await user.type(input, '   ');

    const submitBtn = screen.getByLabelText('Submit query');
    expect(submitBtn).toBeDisabled();

    await user.click(submitBtn);
    expect(mockSubmitQuery).not.toHaveBeenCalled();
  });

  it('submits query on button click with valid input', async () => {
    const user = userEvent.setup();
    render(<ChatBar />);

    const input = screen.getByLabelText('Query input');
    await user.type(input, 'show revenue by region');

    const submitBtn = screen.getByLabelText('Submit query');
    expect(submitBtn).not.toBeDisabled();

    await user.click(submitBtn);
    expect(mockSubmitQuery).toHaveBeenCalledWith('show revenue by region');
  });

  it('submits query on Enter key press', async () => {
    const user = userEvent.setup();
    render(<ChatBar />);

    const input = screen.getByLabelText('Query input');
    await user.type(input, 'total sales{enter}');

    expect(mockSubmitQuery).toHaveBeenCalledWith('total sales');
  });

  it('clears input after successful submission', async () => {
    const user = userEvent.setup();
    render(<ChatBar />);

    const input = screen.getByLabelText('Query input');
    await user.type(input, 'show data');
    await user.click(screen.getByLabelText('Submit query'));

    expect(input).toHaveValue('');
  });

  it('disables input and button while loading', () => {
    mockUseSessionStore.mockImplementation((selector: unknown) => {
      const state = {
        loading: true,
        submitQuery: mockSubmitQuery,
      };
      return (selector as (s: typeof state) => unknown)(state);
    });

    render(<ChatBar />);

    const input = screen.getByLabelText('Query input');
    const submitBtn = screen.getByLabelText('Submit query');

    expect(input).toBeDisabled();
    expect(submitBtn).toBeDisabled();
  });

  it('enforces 500 character max length', async () => {
    const user = userEvent.setup();
    render(<ChatBar />);

    const input = screen.getByLabelText('Query input');
    const longText = 'a'.repeat(600);
    await user.type(input, longText);

    expect((input as HTMLInputElement).value.length).toBeLessThanOrEqual(500);
  });

  it('renders as a fixed bottom bar', () => {
    render(<ChatBar />);

    const form = screen.getByRole('form', { name: 'Chat input' });
    expect(form).toHaveClass('fixed', 'bottom-0');
  });
});
