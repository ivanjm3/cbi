import { useState, useRef, useCallback, useEffect, type FormEvent, type KeyboardEvent } from 'react';
import { useSessionStore } from '../store/sessionStore';

const MAX_INPUT_LENGTH = 500;

/**
 * Check if the Web Speech API (SpeechRecognition) is available in the browser.
 */
function isSpeechRecognitionSupported(): boolean {
  if (typeof window === 'undefined') return false;
  return !!(
    (window as unknown as Record<string, unknown>).SpeechRecognition ||
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition
  );
}

/**
 * Create a SpeechRecognition instance (cross-browser).
 */
function createSpeechRecognition(): SpeechRecognition | null {
  if (typeof window === 'undefined') return null;
  const SpeechRecognitionCtor =
    (window as unknown as Record<string, typeof SpeechRecognition>).SpeechRecognition ||
    (window as unknown as Record<string, typeof SpeechRecognition>).webkitSpeechRecognition;
  if (!SpeechRecognitionCtor) return null;
  return new SpeechRecognitionCtor();
}

export function ChatBar() {
  const [input, setInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const loading = useSessionStore((s) => s.loading);
  const submitQuery = useSessionStore((s) => s.submitQuery);

  const speechSupported = isSpeechRecognitionSupported();

  const canSubmit = input.trim().length > 0 && !loading;

  const handleSubmit = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();
      if (!canSubmit) return;
      const queryText = input.trim();
      setInput('');
      await submitQuery(queryText);
    },
    [canSubmit, input, submitQuery],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
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
      setInput((prev) => {
        const combined = prev + transcript;
        return combined.slice(0, MAX_INPUT_LENGTH);
      });
    };

    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
    };

    recognition.onerror = () => {
      setIsListening(false);
      recognitionRef.current = null;
    };

    recognitionRef.current = recognition;
    setIsListening(true);
    recognition.start();
  }, [speechSupported, isListening]);

  // Clean up recognition on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
        recognitionRef.current = null;
      }
    };
  }, []);

  return (
    <form
      onSubmit={handleSubmit}
      className="fixed bottom-0 left-0 right-0 z-50 flex items-center gap-2 border-t border-gray-200 bg-white px-4 py-3 shadow-lg"
      aria-label="Chat input"
    >
      <input
        ref={inputRef}
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value.slice(0, MAX_INPUT_LENGTH))}
        onKeyDown={handleKeyDown}
        disabled={loading}
        maxLength={MAX_INPUT_LENGTH}
        placeholder="Ask a question about your data..."
        className="flex-1 rounded-lg border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:opacity-60"
        aria-label="Query input"
      />

      {speechSupported && (
        <button
          type="button"
          onClick={startVoiceInput}
          disabled={loading || isListening}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
          aria-label={isListening ? 'Listening...' : 'Voice input'}
          title={isListening ? 'Listening...' : 'Voice input'}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`h-4 w-4 ${isListening ? 'text-red-500 animate-pulse' : ''}`}
          >
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <line x1="12" y1="19" x2="12" y2="23" />
            <line x1="8" y1="23" x2="16" y2="23" />
          </svg>
        </button>
      )}

      <button
        type="submit"
        disabled={!canSubmit}
        className="flex h-9 items-center justify-center rounded-lg bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300 disabled:opacity-60"
        aria-label="Submit query"
      >
        {loading ? (
          <svg
            className="h-4 w-4 animate-spin"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
        ) : (
          'Send'
        )}
      </button>
    </form>
  );
}
