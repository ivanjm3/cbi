/**
 * TopBar component.
 *
 * Contains logo, workspace name input, Save Session button, settings icon.
 * The Save Session button opens a prompt dialog for naming the bookmark.
 *
 * Requirements: 1.1, 8.1, 8.6
 */

import { useCallback, useState } from 'react';
import { useSessionStore } from '../store/sessionStore';
import { SaveSessionModal } from './SaveSessionModal';

export function TopBar() {
  const workspaceName = useSessionStore((s) => s.workspaceName);
  const [showSaveModal, setShowSaveModal] = useState(false);

  const handleSaveClick = useCallback(() => {
    setShowSaveModal(true);
  }, []);

  const handleSaveClose = useCallback(() => {
    setShowSaveModal(false);
  }, []);

  return (
    <>
      <header
        className="flex items-center gap-4 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-2 h-12 min-h-[48px]"
        aria-label="Top bar"
      >
        {/* App logo */}
        <div className="flex items-center gap-2">
          <span className="text-blue-600 dark:text-blue-400 font-bold text-lg" aria-label="App logo">
            ◆
          </span>
          <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            Dboard
          </span>
        </div>

        {/* Workspace name input */}
        <input
          type="text"
          defaultValue={workspaceName}
          maxLength={100}
          placeholder="Untitled Workspace"
          className="flex-1 max-w-xs rounded border border-transparent bg-transparent px-2 py-1 text-sm text-gray-800 dark:text-gray-200 hover:border-gray-300 dark:hover:border-gray-600 focus:border-blue-500 focus:outline-none"
          aria-label="Workspace name"
        />

        <div className="ml-auto flex items-center gap-2">
          {/* Save Session button */}
          <button
            type="button"
            onClick={handleSaveClick}
            className="rounded-lg bg-blue-600 dark:bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors"
          >
            Save Session
          </button>

          {/* Settings icon */}
          <button
            type="button"
            className="rounded p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
            aria-label="Settings"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
          </button>
        </div>
      </header>

      {/* Save Session Modal */}
      {showSaveModal && <SaveSessionModal onClose={handleSaveClose} />}
    </>
  );
}
