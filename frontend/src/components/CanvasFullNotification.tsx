import { useSessionStore } from '../store/sessionStore';

/**
 * Inline notification displayed when the canvas is full and all cards are pinned.
 * Prompts the user to unpin or remove a card before new results can be displayed.
 *
 * Requirements: 10.5
 */
export function CanvasFullNotification() {
  const canvasFullNotification = useSessionStore((s) => s.canvasFullNotification);

  if (!canvasFullNotification) return null;

  return (
    <div
      data-testid="canvas-full-notification"
      role="alert"
      className="mx-4 mt-4 flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800"
    >
      <svg
        className="h-5 w-5 shrink-0 text-amber-500"
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z"
          clipRule="evenodd"
        />
      </svg>
      <span>Canvas full — unpin or remove a card to display new results.</span>
    </div>
  );
}
