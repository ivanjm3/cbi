/**
 * SaveSessionModal component.
 *
 * Prompts the user to enter a session name (max 100 chars) and saves a
 * bookmark containing the current state. Handles localStorage quota exceeded
 * errors gracefully.
 *
 * Requirements: 8.1, 8.6
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useSessionStore } from '../store/sessionStore';

export interface SaveSessionModalProps {
  onClose: () => void;
}

export function SaveSessionModal({ onClose }: SaveSessionModalProps) {
  const saveBookmark = useSessionStore((s) => s.saveBookmark);
  const workspaceName = useSessionStore((s) => s.workspaceName);

  const [name, setName] = useState(workspaceName || '');
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleSave = useCallback(() => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Please enter a session name.');
      return;
    }
    if (trimmed.length > 100) {
      setError('Session name must be 100 characters or fewer.');
      return;
    }

    try {
      saveBookmark(trimmed);
      onClose();
    } catch {
      setError(
        'Unable to save session. Storage may be full — try deleting older bookmarks to free space.',
      );
    }
  }, [name, saveBookmark, onClose]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSave();
      }
    },
    [handleSave],
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-label="Save session"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="mx-4 w-full max-w-sm rounded-lg bg-white dark:bg-gray-800 p-6 shadow-xl">
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
          Save Session
        </h3>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Enter a name for this session bookmark.
        </p>

        <div className="mt-4">
          <input
            ref={inputRef}
            type="text"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setError(null);
            }}
            onKeyDown={handleKeyDown}
            maxLength={100}
            placeholder="My analysis session"
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-label="Session name"
          />
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500 text-right">
            {name.length}/100
          </p>
        </div>

        {/* Error message */}
        {error && (
          <div
            className="mt-2 rounded-md bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-400"
            role="alert"
          >
            {error}
          </div>
        )}

        <div className="mt-4 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-md bg-blue-600 dark:bg-blue-500 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 dark:hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
