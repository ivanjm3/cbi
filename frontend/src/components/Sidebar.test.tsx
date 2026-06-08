/**
 * Unit tests for Sidebar component – Saved Prompts section.
 * Validates: Requirements 8.2, 8.3, 8.5
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Sidebar } from './Sidebar';
import { useSessionStore } from '../store/sessionStore';
import type { SavedPrompt, ChatMessage } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSavedPrompt(overrides: Partial<SavedPrompt> = {}): SavedPrompt {
  return {
    id: crypto.randomUUID(),
    name: 'Test Prompt',
    savedAt: Date.now() - 60 * 60 * 1000, // 1 hour ago
    chatThread: [],
    cards: [],
    ...overrides,
  };
}

function makeUserMessage(content = 'hello'): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'user',
    content,
    timestamp: Date.now(),
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Sidebar – Saved Prompts', () => {
  beforeEach(() => {
    // Reset store to a clean expanded state with no prompts
    useSessionStore.setState({
      sidebarCollapsed: false,
      savedPrompts: [],
      chatHistory: [],
      chatThread: [],
      cards: {},
      activeCardId: null,
      loading: false,
      traceabilityPanelVisible: false,
      statsPanelCollapsed: false,
    });
  });

  describe('Display (Requirement 8.2)', () => {
    it('shows empty state when there are no saved prompts', () => {
      render(<Sidebar />);
      expect(screen.getByText('No saved prompts.')).toBeInTheDocument();
    });

    it('displays saved prompts with name and timestamp', () => {
      const now = Date.now();
      const prompt = makeSavedPrompt({
        name: 'Revenue Analysis',
        savedAt: now - 2 * 60 * 60 * 1000, // 2 hours ago
      });
      useSessionStore.setState({ savedPrompts: [prompt] });

      render(<Sidebar />);
      expect(screen.getByText('Revenue Analysis')).toBeInTheDocument();
      expect(screen.getByText('2 hours ago')).toBeInTheDocument();
    });

    it('displays up to 50 saved prompts', () => {
      const prompts = Array.from({ length: 55 }, (_, i) =>
        makeSavedPrompt({ name: `Prompt ${i}` }),
      );
      useSessionStore.setState({ savedPrompts: prompts });

      render(<Sidebar />);
      // Should only show 50
      const items = screen.getAllByRole('button', { name: /Load saved prompt/ });
      expect(items).toHaveLength(50);
    });

    it('formats timestamps as absolute for entries older than 24h', () => {
      const oldTimestamp = Date.now() - 48 * 60 * 60 * 1000; // 2 days ago
      const prompt = makeSavedPrompt({ savedAt: oldTimestamp });
      useSessionStore.setState({ savedPrompts: [prompt] });

      render(<Sidebar />);
      // Should show YYYY-MM-DD HH:mm format
      const datePattern = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;
      const timestampEl = screen.getByText(datePattern);
      expect(timestampEl).toBeInTheDocument();
    });

    it('orders prompts most recently saved first', () => {
      const now = Date.now();
      const older = makeSavedPrompt({
        name: 'Older Prompt',
        savedAt: now - 5 * 60 * 60 * 1000,
      });
      const newer = makeSavedPrompt({
        name: 'Newer Prompt',
        savedAt: now - 1 * 60 * 60 * 1000,
      });
      // Store them with newer first (as the store does)
      useSessionStore.setState({ savedPrompts: [newer, older] });

      render(<Sidebar />);
      const buttons = screen.getAllByRole('button', { name: /Load saved prompt/ });
      expect(buttons[0]).toHaveTextContent('Newer Prompt');
      expect(buttons[1]).toHaveTextContent('Older Prompt');
    });
  });

  describe('Delete with confirmation (Requirement 8.5)', () => {
    it('shows delete confirmation modal when delete is clicked', async () => {
      const user = userEvent.setup();
      const prompt = makeSavedPrompt({ name: 'My Analysis' });
      useSessionStore.setState({ savedPrompts: [prompt] });

      render(<Sidebar />);

      const deleteBtn = screen.getByLabelText('Delete saved prompt: My Analysis');
      await user.click(deleteBtn);

      expect(screen.getByText('Delete Saved Prompt')).toBeInTheDocument();
      expect(screen.getByText(/Are you sure you want to delete/)).toBeInTheDocument();
      // The modal contains the prompt name in a confirmation message
      const dialog = screen.getByRole('dialog', { name: /Confirm saved prompt deletion/ });
      expect(dialog).toBeInTheDocument();
    });

    it('removes the prompt when deletion is confirmed', async () => {
      const user = userEvent.setup();
      const prompt = makeSavedPrompt({ name: 'To Delete' });
      useSessionStore.setState({ savedPrompts: [prompt] });

      render(<Sidebar />);

      const deleteBtn = screen.getByLabelText('Delete saved prompt: To Delete');
      await user.click(deleteBtn);

      const confirmBtn = screen.getByRole('button', { name: 'Delete' });
      await user.click(confirmBtn);

      expect(useSessionStore.getState().savedPrompts).toHaveLength(0);
    });

    it('cancels deletion when cancel is clicked', async () => {
      const user = userEvent.setup();
      const prompt = makeSavedPrompt({ name: 'Keep Me' });
      useSessionStore.setState({ savedPrompts: [prompt] });

      render(<Sidebar />);

      const deleteBtn = screen.getByLabelText('Delete saved prompt: Keep Me');
      await user.click(deleteBtn);

      const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
      await user.click(cancelBtn);

      expect(useSessionStore.getState().savedPrompts).toHaveLength(1);
      // Modal should be dismissed
      expect(screen.queryByText('Delete Saved Prompt')).not.toBeInTheDocument();
    });
  });

  describe('Load with unsaved-changes warning (Requirement 8.3)', () => {
    it('loads directly when there are no unsaved changes', async () => {
      const user = userEvent.setup();
      const prompt = makeSavedPrompt({
        name: 'Direct Load',
        chatThread: [makeUserMessage('saved query')],
      });
      useSessionStore.setState({ savedPrompts: [prompt], chatThread: [] });

      render(<Sidebar />);

      const loadBtn = screen.getByLabelText('Load saved prompt: Direct Load');
      await user.click(loadBtn);

      // Should load immediately without confirmation
      expect(screen.queryByText('Load Saved Prompt')).not.toBeInTheDocument();
      const state = useSessionStore.getState();
      expect(state.chatThread).toHaveLength(1);
      expect(state.chatThread[0].content).toBe('saved query');
    });

    it('shows unsaved-changes warning when session has messages', async () => {
      const user = userEvent.setup();
      const prompt = makeSavedPrompt({ name: 'Load This' });
      useSessionStore.setState({
        savedPrompts: [prompt],
        chatThread: [makeUserMessage('existing work')],
      });

      render(<Sidebar />);

      const loadBtn = screen.getByLabelText('Load saved prompt: Load This');
      await user.click(loadBtn);

      expect(screen.getByText('Load Saved Prompt')).toBeInTheDocument();
      expect(screen.getByText(/unsaved changes/)).toBeInTheDocument();
    });

    it('replaces session state when load is confirmed', async () => {
      const user = userEvent.setup();
      const savedMsg = makeUserMessage('restored query');
      const prompt = makeSavedPrompt({
        name: 'Confirm Load',
        chatThread: [savedMsg],
      });
      useSessionStore.setState({
        savedPrompts: [prompt],
        chatThread: [makeUserMessage('current work')],
      });

      render(<Sidebar />);

      const loadBtn = screen.getByLabelText('Load saved prompt: Confirm Load');
      await user.click(loadBtn);

      const confirmBtn = screen.getByRole('button', { name: 'Load' });
      await user.click(confirmBtn);

      const state = useSessionStore.getState();
      expect(state.chatThread).toHaveLength(1);
      expect(state.chatThread[0].content).toBe('restored query');
    });

    it('cancels load when cancel is clicked', async () => {
      const user = userEvent.setup();
      const prompt = makeSavedPrompt({ name: 'Cancel Load' });
      useSessionStore.setState({
        savedPrompts: [prompt],
        chatThread: [makeUserMessage('keep this')],
      });

      render(<Sidebar />);

      const loadBtn = screen.getByLabelText('Load saved prompt: Cancel Load');
      await user.click(loadBtn);

      const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
      await user.click(cancelBtn);

      // Original session preserved
      const state = useSessionStore.getState();
      expect(state.chatThread).toHaveLength(1);
      expect(state.chatThread[0].content).toBe('keep this');
      // Modal dismissed
      expect(screen.queryByText('Load Saved Prompt')).not.toBeInTheDocument();
    });
  });
});
