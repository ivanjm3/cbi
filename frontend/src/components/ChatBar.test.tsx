/**
 * Unit tests for ChatBar component.
 *
 * Tests cover:
 * - Rendering with correct aria-label and placeholder
 * - 500-char max enforcement
 * - Submit on button click and Enter key
 * - Prevent submission on empty/whitespace-only input
 * - Disable input/button while loading
 * - Voice icon hidden when unsupported, shown when supported
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatBar } from './ChatBar';

// Mock the session store
const mockSubmitQuery = vi.fn();
let mockLoading = false;

vi.mock('../store/sessionStore', () => ({
  useSessionStore: (selector: any) => {
    const state = {
      loading: mockLoading,
      submitQuery: mockSubmitQuery,
    };
    return selector(state);
  },
}));

describe('ChatBar', () => {
  beforeEach(() => {
    mockLoading = false;
    mockSubmitQuery.mockClear();
    // Default: no speech support
    (window as any).SpeechRecognition = undefined;
    (window as any).webkitSpeechRecognition = undefined;
  });

  afterEach(() => {
    delete (window as any).SpeechRecognition;
    delete (window as any).webkitSpeechRecognition;
  });

  it('renders with the correct aria-label', () => {
    render(<ChatBar />);
    expect(screen.getByLabelText('Chat bar')).toBeInTheDocument();
  });

  it('renders a text input with the correct placeholder', () => {
    render(<ChatBar />);
    const input = screen.getByPlaceholderText('Ask a question about your data...');
    expect(input).toBeInTheDocument();
    expect(input).not.toBeDisabled();
  });

  it('renders a submit button', () => {
    render(<ChatBar />);
    const button = screen.getByLabelText('Submit query');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Send');
  });

  it('enforces 500-char max on the input', async () => {
    render(<ChatBar />);
    const input = screen.getByLabelText('Query input') as HTMLInputElement;
    const longText = 'a'.repeat(600);

    await userEvent.type(input, longText);

    expect(input.value.length).toBeLessThanOrEqual(500);
  });

  it('submits on button click with valid input', async () => {
    render(<ChatBar />);
    const input = screen.getByLabelText('Query input');
    const button = screen.getByLabelText('Submit query');

    await userEvent.type(input, 'show revenue');
    await userEvent.click(button);

    expect(mockSubmitQuery).toHaveBeenCalledWith('show revenue');
  });

  it('submits on Enter key with valid input', async () => {
    render(<ChatBar />);
    const input = screen.getByLabelText('Query input');

    await userEvent.type(input, 'show revenue{enter}');

    expect(mockSubmitQuery).toHaveBeenCalledWith('show revenue');
  });

  it('clears input after successful submission', async () => {
    render(<ChatBar />);
    const input = screen.getByLabelText('Query input') as HTMLInputElement;

    await userEvent.type(input, 'show revenue{enter}');

    expect(input.value).toBe('');
  });

  it('prevents submission on empty input', async () => {
    render(<ChatBar />);
    const button = screen.getByLabelText('Submit query');

    await userEvent.click(button);

    expect(mockSubmitQuery).not.toHaveBeenCalled();
  });

  it('prevents submission on whitespace-only input', async () => {
    render(<ChatBar />);
    const input = screen.getByLabelText('Query input');
    const button = screen.getByLabelText('Submit query');

    await userEvent.type(input, '   ');
    await userEvent.click(button);

    expect(mockSubmitQuery).not.toHaveBeenCalled();
  });

  it('prevents submission on Enter with whitespace-only input', async () => {
    render(<ChatBar />);
    const input = screen.getByLabelText('Query input');

    await userEvent.type(input, '   {enter}');

    expect(mockSubmitQuery).not.toHaveBeenCalled();
  });

  it('disables input and button while loading', () => {
    mockLoading = true;
    render(<ChatBar />);

    const input = screen.getByLabelText('Query input');
    const button = screen.getByLabelText('Submit query');

    expect(input).toBeDisabled();
    expect(button).toBeDisabled();
  });

  it('hides voice icon when Web Speech API is not supported', () => {
    render(<ChatBar />);
    const voiceButton = screen.queryByLabelText('Start voice input');
    expect(voiceButton).not.toBeInTheDocument();
  });

  it('shows voice icon when Web Speech API is supported', () => {
    (window as any).SpeechRecognition = vi.fn();
    render(<ChatBar />);
    const voiceButton = screen.getByLabelText('Start voice input');
    expect(voiceButton).toBeInTheDocument();
  });

  it('starts voice recognition on voice icon click', () => {
    const mockStart = vi.fn();
    class MockRecognition {
      continuous = false;
      interimResults = false;
      lang = '';
      onresult: any = null;
      onerror: any = null;
      onend: any = null;
      start = mockStart;
      stop = vi.fn();
      abort = vi.fn();
    }
    (window as any).SpeechRecognition = MockRecognition;

    render(<ChatBar />);
    const voiceButton = screen.getByLabelText('Start voice input');

    fireEvent.click(voiceButton);

    expect(mockStart).toHaveBeenCalled();
  });

  it('appends transcribed text to input on voice result', async () => {
    let recognitionInstance: any;
    class MockRecognition {
      continuous = false;
      interimResults = false;
      lang = '';
      onresult: any = null;
      onerror: any = null;
      onend: any = null;
      start = vi.fn();
      stop = vi.fn();
      abort = vi.fn();
      constructor() {
        recognitionInstance = this;
      }
    }
    (window as any).SpeechRecognition = MockRecognition;

    render(<ChatBar />);
    const input = screen.getByLabelText('Query input') as HTMLInputElement;
    const voiceButton = screen.getByLabelText('Start voice input');

    // Type some text first
    await userEvent.type(input, 'hello ');

    // Click voice button to start recognition
    fireEvent.click(voiceButton);

    // Simulate speech result
    act(() => {
      recognitionInstance.onresult({
        results: [[{ transcript: 'world' }]],
      });
    });

    expect(input.value).toBe('hello world');
  });

  it('disables voice button while loading', () => {
    mockLoading = true;
    (window as any).SpeechRecognition = vi.fn();
    render(<ChatBar />);
    const voiceButton = screen.getByLabelText('Start voice input');
    expect(voiceButton).toBeDisabled();
  });
});
