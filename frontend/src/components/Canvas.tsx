/**
 * Canvas placeholder component.
 * Full implementation in task 6.6 — will include CSS Grid, drag-and-drop, empty state.
 *
 * On narrow screens (<1024px), forces single-column layout regardless of card count.
 *
 * Requirements: 1.3, 1.4, 1.7, 1.5, 1.6
 */

export function Canvas() {
  return (
    <main
      className="flex-1 min-w-0 max-w-full h-full overflow-y-auto p-4"
      aria-label="Canvas"
    >
      {/* Grid: 2-col on desktop, single-col on narrow */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 h-full">
        {/* Empty state — shown when no cards */}
        <div className="col-span-1 lg:col-span-2 flex items-center justify-center h-full">
          <div className="text-center">
            <h2 className="text-lg font-medium text-gray-700 dark:text-gray-300">
              No visualizations yet
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Ask a question using the chat bar below
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
