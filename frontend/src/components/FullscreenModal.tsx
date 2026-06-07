import { useEffect, useCallback } from 'react';

interface FullscreenModalProps {
  children: React.ReactNode;
  onClose: () => void;
}

/**
 * FullscreenModal - Expands card content to fill the viewport as a modal overlay.
 * Closes on close-button click or Escape key press.
 * Requirements: 5.4
 */
export default function FullscreenModal({ children, onClose }: FullscreenModalProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);

  return (
    <div
      data-testid="fullscreen-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      role="dialog"
      aria-modal="true"
    >
      <div className="relative w-full h-full bg-white overflow-auto p-6">
        <button
          data-testid="fullscreen-modal-close"
          onClick={onClose}
          className="absolute top-4 right-4 z-10 rounded-full p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
        {children}
      </div>
    </div>
  );
}
