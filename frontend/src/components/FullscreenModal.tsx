/**
 * FullscreenModal component.
 *
 * Expands a Visualization Card to fill the viewport as a modal overlay.
 * Closes on button click or Escape key press.
 *
 * Requirements: 5.4
 */

import { useCallback, useEffect, useRef } from 'react';
import type { CardState } from '../types';
import { ChartRenderer } from './ChartRenderer';

export interface FullscreenModalProps {
  card: CardState;
  onClose: () => void;
}

export function FullscreenModal({ card, onClose }: FullscreenModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Close on Escape key
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

  // Focus the close button when modal opens for accessibility
  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);

  // Prevent body scroll while modal is open
  useEffect(() => {
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, []);

  // Close when clicking the overlay backdrop (not the content)
  const handleOverlayClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === overlayRef.current) {
        onClose();
      }
    },
    [onClose],
  );

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal="true"
      aria-label={`Fullscreen view: ${card.query}`}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    >
      <div className="relative w-[95vw] h-[90vh] bg-white dark:bg-gray-900 rounded-lg shadow-2xl flex flex-col overflow-hidden">
        {/* Header with query and close button */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
          <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 truncate pr-4">
            {card.query}
          </h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="flex-shrink-0 p-2 rounded-lg text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            title="Close fullscreen (Escape)"
            aria-label="Close fullscreen"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Chart content expanded to fill available space */}
        <div className="flex-1 min-h-0 p-6 flex items-center justify-center">
          <div className="w-full h-full max-h-full" data-fullscreen-chart="true">
            <ChartRenderer renderedOutput={card.renderedOutput} fullscreen />
          </div>
        </div>
      </div>
    </div>
  );
}
