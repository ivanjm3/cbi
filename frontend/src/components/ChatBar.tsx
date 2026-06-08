/**
 * ChatBar component — fixed at the bottom of the center column.
 *
 * Features:
 * - Text input (500-char max) with placeholder "Ask a question about your data..."
 * - Submit button (Enter key or click)
 * - Voice-input icon (Web Speech API, hidden if unsupported)
 * - Prevents submission on empty/whitespace-only input
 * - Disables input and button while request is in flight
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { useSessionStore } from '../store/sessionStore';

// Check if Web Speech API is available
function isSpeechRecognitionSupported(): boolean {
  return !!(
    (window as any).SpeechRecognition ||
    (window as any).webkitSpeechRecognition
  );
}

export function ChatBar() {
  const [input, setInput] = useState('');
  const [listening, setListening] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const recognitionRef = useRef<any>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const loading = useSessionStore((s) => s.loading);
  const submitQuery = useSessionStore((s) => s.submitQuery);

  // Check speech support on mount
  useEffect(() => {
    setSpeechSupported(isSpeechRecognitionSupported());
  }, []);

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    submitQuery(trimmed);
    setInput('');
  }, [input, loading, submitQuery]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleVoiceClick = useCallback(() => {
    if (listening && recognitionRef.current) {
      recognitionRef.current.stop();
      setListening(false);
      return;
    }

    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onresult = (event: any) => {
      const transcript = event.results[0]?.[0]?.transcript ?? '';
      setInput((prev) => {
        const combined = prev + transcript;
        return combined.slice(0, 500);
      });
      setListening(false);
    };

    recognition.onerror = () => {
      setListening(false);
    };

    recognition.onend = () => {
      setListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }, [listening]);

  // Cleanup recognition on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // Ignore abort errors
        }
      }
    };
  }, []);

  const isSubmitDisabled = loading || !input.trim();

  return (
    <div
      className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3"
      aria-label="Chat bar"
    >
      <div className="flex items-center gap-2">
        {/* Voice input button — hidden if unsupported */}
        {speechSupported && (
          <button
            type="button"
            onClick={handleVoiceClick}
            disabled={loading}
            className={`flex items-center justify-center w-9 h-9 rounded-lg transition-colors ${
              listening
                ? 'bg-red-100 text-red-600 dark:bg-red-900 dark:text-red-300'
                : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
            aria-label={listening ? 'Stop voice input' : 'Start voice input'}
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
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
              />
            </svg>
          </button>
        )}

        {/* Text input */}
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value.slice(0, 500))}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about your data..."
          maxLength={500}
          disabled={loading}
          className="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label="Query input"
        />

        {/* Submit button */}
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSubmitDisabled}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label="Submit query"
        >
          Send
        </button>
      </div>
    </div>
  );
}
