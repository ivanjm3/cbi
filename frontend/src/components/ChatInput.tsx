/**
 * ChatInput component — fixed at the bottom of the main content area.
 *
 * Features:
 * - Text input with 500-character maximum
 * - Submit button (disabled when empty/whitespace-only or loading)
 * - Voice-input icon using Web Speech API (hidden if browser unsupported)
 * - Prevents submission on empty/whitespace-only input
 * - Disables input and submit while request is in flight
 * - On submit: dispatches to store submitQuery (which appends user bubble + sends API request)
 * - Enter key submits the form
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useSessionStore } from '../store/sessionStore';

/**
 * Check if Web Speech API is available in the current browser.
 */
function isSpeechRecognitionSupported(): boolean {
  return !!(
    (window as unknown as Record<string, unknown>).SpeechRecognition ||
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition
  );
}

/**
 * Create a SpeechRecognition instance (cross-browser).
 */
function createSpeechRecognition(): SpeechRecognition | null {
  const SpeechRecognitionCtor =
    (window as unknown as Record<string, unknown>).SpeechRecognition ||
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
  if (!SpeechRecognitionCtor) return null;
  return new (SpeechRecognitionCtor as new () => SpeechRecognition)();
}

export function ChatInput() {
  const [input, setInput] = useState('');
  const [speechSupported, setSpeechSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  const submitQuery = useSessionStore((s) => s.submitQuery);
  const loading = useSessionStore((s) => s.loading);

  // Check for Web Speech API support on mount
  useEffect(() => {
    setSpeechSupported(isSpeechRecognitionSupported());
  }, []);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = input.trim();
      if (!trimmed || loading) return;
      submitQuery(trimmed);
      setInput('');
    },
    [input, loading, submitQuery],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const trimmed = input.trim();
        if (!trimmed || loading) return;
        submitQuery(trimmed);
        setInput('');
      }
    },
    [input, loading, submitQuery],
  );

  const startVoiceInput = useCallback(() => {
    if (!speechSupported || isListening) return;

    const recognition = createSpeechRecognition();
    if (!recognition) return;

    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = event.results[0]?.[0]?.transcript ?? '';
      if (transcript) {
        setInput((prev) => {
          const combined = prev ? `${prev} ${transcript}` : transcript;
          // Respect the 500-char max
          return combined.slice(0, 500);
        });
      }
    };

    recognition.onerror = () => {
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
    };

    recognitionRef.current = recognition;
    setIsListening(true);
    recognition.start();
  }, [speechSupported, isListening]);

  const stopVoiceInput = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setIsListening(false);
  }, []);

  const toggleVoiceInput = useCallback(() => {
    if (isListening) {
      stopVoiceInput();
    } else {
      startVoiceInput();
    }
  }, [isListening, startVoiceInput, stopVoiceInput]);

  // Cleanup recognition on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
        recognitionRef.current = null;
      }
    };
  }, []);

  const canSubmit = !!input.trim() && !loading;

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-2 border-t border-border-default bg-bg-secondary px-4 py-3"
      aria-label="Chat input"
    >
      {/* Voice input button — hidden if Web Speech API unsupported */}
      {speechSupported && (
        <button
          type="button"
          onClick={toggleVoiceInput}
          disabled={loading}
          aria-label={isListening ? 'Stop voice input' : 'Start voice input'}
          className={`flex-shrink-0 rounded-lg p-2 transition-colors focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed ${
            isListening
              ? 'bg-status-error text-white'
              : 'text-text-muted hover:text-text-primary hover:bg-bg-input'
          }`}
        >
          <MicrophoneIcon />
        </button>
      )}

      {/* Text input */}
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask a question about your data..."
        maxLength={500}
        disabled={loading}
        aria-label="Query input"
        className="flex-1 rounded-lg border border-border-default bg-bg-input px-4 py-2 text-base text-text-primary placeholder:text-text-muted focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary disabled:opacity-50"
      />

      {/* Submit button */}
      <button
        type="submit"
        disabled={!canSubmit}
        aria-label="Submit query"
        className="flex-shrink-0 rounded-lg bg-accent-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <SendIcon />
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function MicrophoneIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5"
      aria-hidden="true"
    >
      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" x2="12" y1="19" y2="22" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
      aria-hidden="true"
    >
      <path d="m22 2-7 20-4-9-9-4Z" />
      <path d="M22 2 11 13" />
    </svg>
  );
}
