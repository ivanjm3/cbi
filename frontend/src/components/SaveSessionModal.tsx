/**
 * SaveSessionModal component.
 *
 * Prompts the user to enter a session name (max 100 chars) and saves the
 * current session as a SavedPrompt. Handles localStorage quota exceeded
 * errors gracefully with a user-facing error message.
 *
 * Requirements: 8.1, 8.6
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useSessionStore } from '../store/sessionStore';

export interface SaveSessionModalProps {
  onClose: () => void;
}

export function SaveSessionModal({ onClose }: SaveSessionModalProps) {
  const saveSavedPrompt = useSessionStore((s) => s.saveSavedPrompt);
  const storageError = useSessionStore((s) => s.storageError);
  const clearStorageError = useSessionStore((s) => s.clearStorageError);

  const [name, setName] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
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

  // Clear storage error on unmount
  useEffect(() => {
    return () => {
      clearStorageError();
    };
  }, [clearStorageError]);

  const handleSave = useCallback(() => {
    const trimmed = name.trim();
    if (!trimmed) {
      setLocalError('Please enter a session name.');
      return;
    }
    if (trimmed.length > 100) {
      setLocalError('Session name must be 100 characters or fewer.');
      return;
    }

    // Clear any previous errors
    setLocalError(null);
    clearStorageError();

    // Attempt save — store will set storageError on quota exceeded
    saveSavedPrompt(trimmed);

    // Check if the store reported a storage error (set synchronously)
    const currentError = useSessionStore.getState().storageError;
    if (!currentError) {
      onClose();
    }
    // If there's a storage error, the modal stays open showing the error
  }, [name, saveSavedPrompt, clearStorageError, onClose]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSave();
      }
    },
    [handleSave],
  );

  const displayError = localError || storageError;

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
      <div className="mx-4 w-full max-w-sm rounded-lg bg-bg-secondary p-6 shadow-panel">
        <h3 className="text-base font-semibold text-text-primary">
          Save Session
        </h3>
        <p className="mt-1 text-sm text-text-secondary">
          Enter a name for this saved prompt.
        </p>

        <div className="mt-4">
          <input
            ref={inputRef}
            type="text"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setLocalError(null);
            }}
            onKeyDown={handleKeyDown}
            maxLength={100}
            placeholder="My analysis session"
            className="w-full rounded-md border border-border-default bg-bg-input px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary"
            aria-label="Session name"
          />
          <p className="mt-1 text-xs text-text-muted text-right">
            {name.length}/100
          </p>
        </div>

        {/* Error message */}
        {displayError && (
          <div
            className="mt-2 rounded-md bg-red-50 px-3 py-2 text-sm text-status-error"
            role="alert"
          >
            {displayError}
          </div>
        )}

        <div className="mt-4 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-3 py-2 text-sm font-medium text-text-secondary hover:bg-bg-input"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-md bg-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent-primary"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
