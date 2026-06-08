/**
 * Unit tests for ErrorMessage component.
 * Validates: Requirements 9.3, 9.4, 9.5
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ErrorMessage } from './ErrorMessage';
import { useSessionStore } from '../store/sessionStore';
import type { ChatMessage } from '../types';

describe('ErrorMessage', () => {
  beforeEach(() => {
    useSessionStore.setState({
      chatThread: [],
      cards: {},
      activeCardId: null,
      loading: false,
      sidebarCollapsed: false,
      traceabilityPanelVisible: false,
      statsPanelCollapsed: false,
      savedPrompts: [],
      chatHistory: [],
      storageError: null,
    });
  });

  function makeErrorMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
    return {
      id: 'err-1',
      role: 'error',
      content: 'Something went wrong',
      timestamp: Date.now(),
      ...overrides,
    };
  }

  describe('422 errors (Requirement 9.3)', () => {
    it('displays the error_message content as left-aligned in chat thread', () => {
      const message = makeErrorMessage({
        content: 'Could not interpret your question. Try rephrasing.',
        statusCode: 422,
        originalQuery: 'show me data',
      });

      render(<ErrorMessage message={message} />);

      expect(
        screen.getByText('Could not interpret your question. Try rephrasing.'),
      ).toBeInTheDocument();
    });

    it('shows "Query Error" label for 422 status', () => {
      const message = makeErrorMessage({
        content: 'Invalid query',
        statusCode: 422,
      });

      render(<ErrorMessage message={message} />);

      expect(screen.getByText('Query Error')).toBeInTheDocument();
    });

    it('does NOT render a retry button for 422 errors', () => {
      const message = makeErrorMessage({
        content: 'Invalid query',
        statusCode: 422,
        originalQuery: 'bad query',
      });

      render(<ErrorMessage message={message} />);

      expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
    });

    it('renders with role="alert" for accessibility', () => {
      const message = makeErrorMessage({ statusCode: 422 });

      render(<ErrorMessage message={message} />);

      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  describe('503/504 errors (Requirement 9.4)', () => {
    it('displays service unavailability message for 503', () => {
      const message = makeErrorMessage({
        content: 'Service is temporarily unavailable. Please try again later.',
        statusCode: 503,
        originalQuery: 'show revenue',
      });

      render(<ErrorMessage message={message} />);

      expect(
        screen.getByText('Service is temporarily unavailable. Please try again later.'),
      ).toBeInTheDocument();
      expect(screen.getByText('Service Unavailable')).toBeInTheDocument();
    });

    it('displays service unavailability message for 504', () => {
      const message = makeErrorMessage({
        content: 'Gateway timeout. The service did not respond in time.',
        statusCode: 504,
        originalQuery: 'show revenue',
      });

      render(<ErrorMessage message={message} />);

      expect(screen.getByText('Service Unavailable')).toBeInTheDocument();
    });

    it('renders a retry button for 503 errors', () => {
      const message = makeErrorMessage({
        content: 'Service unavailable',
        statusCode: 503,
        originalQuery: 'show revenue',
      });

      render(<ErrorMessage message={message} />);

      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    it('renders a retry button for 504 errors', () => {
      const message = makeErrorMessage({
        content: 'Gateway timeout',
        statusCode: 504,
        originalQuery: 'show revenue',
      });

      render(<ErrorMessage message={message} />);

      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    it('retry button re-sends identical POST /query with same query_text', async () => {
      const user = userEvent.setup();
      const submitQuerySpy = vi.fn();
      useSessionStore.setState({ submitQuery: submitQuerySpy } as any);

      const message = makeErrorMessage({
        content: 'Service unavailable',
        statusCode: 503,
        originalQuery: 'show me quarterly revenue',
      });

      render(<ErrorMessage message={message} />);

      const retryButton = screen.getByRole('button', { name: /retry/i });
      await user.click(retryButton);

      expect(submitQuerySpy).toHaveBeenCalledTimes(1);
      expect(submitQuerySpy).toHaveBeenCalledWith('show me quarterly revenue');
    });
  });

  describe('Timeout errors (Requirement 9.5)', () => {
    it('displays timeout message for 408 status', () => {
      const message = makeErrorMessage({
        content: 'Request timed out after 60s',
        statusCode: 408,
        originalQuery: 'complex query',
      });

      render(<ErrorMessage message={message} />);

      expect(screen.getByText('Request timed out after 60s')).toBeInTheDocument();
      expect(screen.getByText('Request Timeout')).toBeInTheDocument();
    });

    it('renders a retry button for timeout errors', () => {
      const message = makeErrorMessage({
        content: 'Request timed out',
        statusCode: 408,
        originalQuery: 'complex query',
      });

      render(<ErrorMessage message={message} />);

      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    it('retry button re-sends the original query on timeout', async () => {
      const user = userEvent.setup();
      const submitQuerySpy = vi.fn();
      useSessionStore.setState({ submitQuery: submitQuerySpy } as any);

      const message = makeErrorMessage({
        content: 'Request timed out',
        statusCode: 408,
        originalQuery: 'long running analysis',
      });

      render(<ErrorMessage message={message} />);

      const retryButton = screen.getByRole('button', { name: /retry/i });
      await user.click(retryButton);

      expect(submitQuerySpy).toHaveBeenCalledWith('long running analysis');
    });
  });

  describe('General behavior', () => {
    it('does not render retry button when originalQuery is missing', () => {
      const message = makeErrorMessage({
        content: 'Service unavailable',
        statusCode: 503,
        // no originalQuery
      });

      render(<ErrorMessage message={message} />);

      expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
    });

    it('renders "Error" label for unknown status codes', () => {
      const message = makeErrorMessage({
        content: 'Unknown error',
        statusCode: 500,
      });

      render(<ErrorMessage message={message} />);

      expect(screen.getByText('Error')).toBeInTheDocument();
    });

    it('is left-aligned in the chat thread', () => {
      const message = makeErrorMessage({ statusCode: 422 });

      const { container } = render(<ErrorMessage message={message} />);

      const wrapper = container.firstChild as HTMLElement;
      expect(wrapper.className).toContain('justify-start');
    });
  });
});
