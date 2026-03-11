"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import clsx from "clsx";
import { useWebSocket } from "@/lib/ws";
import { useStore, ChatMessage } from "@/lib/store";

/** Quick-ask buttons for common race engineer questions. */
const QUICK_ASKS = [
  { label: "Tire Life", question: "How much tire life do I have left?" },
  { label: "Pit Window", question: "When should I pit?" },
  { label: "Sector Analysis", question: "Where am I losing time?" },
  { label: "Sim vs Real", question: "How does my sim pace compare to real?" },
  { label: "Setup Tips", question: "What setup changes for more rear grip?" },
];

/** Single chat message bubble. */
function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  return (
    <div
      className={clsx(
        "flex gap-2 animate-fade-in",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <div
        className={clsx(
          "w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-data-xs font-mono font-bold",
          isUser
            ? "bg-telemetry-speed/20 text-telemetry-speed"
            : isSystem
              ? "bg-race-border text-race-muted"
              : "bg-telemetry-throttle/20 text-telemetry-throttle"
        )}
      >
        {isUser ? "DRV" : isSystem ? "SYS" : "ENG"}
      </div>

      {/* Message content */}
      <div
        className={clsx(
          "max-w-[85%] rounded-lg px-3 py-2",
          isUser
            ? "bg-telemetry-speed/10 border border-telemetry-speed/20"
            : isSystem
              ? "bg-race-surface border border-race-border"
              : "bg-race-card border border-race-border"
        )}
      >
        {isUser ? (
          <p className="text-data-sm text-race-text">{message.content}</p>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none">
            <ReactMarkdown
              components={{
                p: ({ children }) => (
                  <p className="text-data-sm text-race-text mb-2 last:mb-0">
                    {children}
                  </p>
                ),
                strong: ({ children }) => (
                  <strong className="text-telemetry-speed font-mono font-semibold">
                    {children}
                  </strong>
                ),
                li: ({ children }) => (
                  <li className="text-data-sm text-race-text ml-4 list-disc">
                    {children}
                  </li>
                ),
                code: ({ children }) => (
                  <code className="font-mono text-data-xs bg-race-surface px-1 py-0.5 rounded text-telemetry-gear">
                    {children}
                  </code>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {/* Metadata footer */}
        {message.intent && !isUser && (
          <div className="flex items-center gap-2 mt-2 pt-1.5 border-t border-race-border">
            <span className="text-data-xs font-mono text-race-muted">
              {message.intent}
            </span>
            {message.sources && (
              <span className="text-data-xs font-mono text-race-muted">
                {Object.entries(message.sources)
                  .filter(([, v]) => v > 0)
                  .map(([k, v]) => `${k}:${v}`)
                  .join(" ")}
              </span>
            )}
            {message.elapsed_ms !== undefined && (
              <span className="text-data-xs font-mono text-race-muted ml-auto">
                {message.elapsed_ms}ms
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** Streaming indicator dots. */
function StreamingIndicator() {
  return (
    <div className="flex gap-2 items-start">
      <div className="w-7 h-7 rounded-full bg-telemetry-throttle/20 flex items-center justify-center flex-shrink-0">
        <span className="text-data-xs font-mono font-bold text-telemetry-throttle">
          ENG
        </span>
      </div>
      <div className="bg-race-card border border-race-border rounded-lg px-3 py-2">
        <div className="flex gap-1">
          <div className="w-1.5 h-1.5 rounded-full bg-telemetry-throttle animate-bounce [animation-delay:0ms]" />
          <div className="w-1.5 h-1.5 rounded-full bg-telemetry-throttle animate-bounce [animation-delay:150ms]" />
          <div className="w-1.5 h-1.5 rounded-full bg-telemetry-throttle animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    </div>
  );
}

export default function RaceEngineerChat() {
  const {
    chatMessages,
    isChatStreaming,
    addChatMessage,
    appendToLastMessage,
    setChatStreaming,
  } = useStore();

  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // WebSocket connection for streaming chat
  const onMessage = useCallback(
    (data: unknown) => {
      const msg = data as Record<string, unknown>;
      if (!msg || typeof msg !== "object") return;

      switch (msg.type) {
        case "intent":
          // Intent detected -- assistant message will follow
          break;

        case "chunk":
          appendToLastMessage(msg.content as string);
          break;

        case "response":
          // Non-streaming fallback -- complete response
          appendToLastMessage(msg.content as string);
          break;

        case "complete": {
          setChatStreaming(false);
          // Update last message with metadata
          const messages = useStore.getState().chatMessages;
          if (messages.length > 0) {
            const last = messages[messages.length - 1];
            if (last.role === "assistant") {
              last.elapsed_ms = msg.elapsed_ms as number;
              last.sources = msg.sources as Record<string, number>;
            }
          }
          break;
        }

        case "error":
          setChatStreaming(false);
          addChatMessage({
            id: `err-${Date.now()}`,
            role: "system",
            content: `Error: ${msg.message}`,
            timestamp: Date.now(),
          });
          break;
      }
    },
    [addChatMessage, appendToLastMessage, setChatStreaming]
  );

  const { send, state: wsState } = useWebSocket({
    url: `ws://${typeof window !== "undefined" ? window.location.hostname : "localhost"}:8000/api/ws/chat`,
    onMessage,
  });

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages, isChatStreaming]);

  const handleSubmit = useCallback(
    (question: string) => {
      if (!question.trim() || isChatStreaming) return;

      // Add user message
      addChatMessage({
        id: `user-${Date.now()}`,
        role: "user",
        content: question.trim(),
        timestamp: Date.now(),
      });

      // Add empty assistant message for streaming into
      addChatMessage({
        id: `asst-${Date.now()}`,
        role: "assistant",
        content: "",
        timestamp: Date.now(),
      });

      setChatStreaming(true);
      send({ message: question.trim() });
      setInput("");
    },
    [addChatMessage, setChatStreaming, send, isChatStreaming]
  );

  const onFormSubmit = (e: FormEvent) => {
    e.preventDefault();
    handleSubmit(input);
  };

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <span className="panel-title">Race Engineer</span>
          <span
            className={clsx(
              "text-data-xs font-mono px-1.5 py-0.5 rounded",
              wsState === "connected"
                ? "bg-telemetry-throttle/20 text-telemetry-throttle"
                : "bg-telemetry-brake/20 text-telemetry-brake"
            )}
          >
            {wsState === "connected" ? "LIVE" : "OFFLINE"}
          </span>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3 min-h-0">
        {chatMessages.length === 0 && (
          <div className="flex-1 flex items-center justify-center text-center">
            <div>
              <div className="w-12 h-12 rounded-full bg-telemetry-throttle/10 flex items-center justify-center mx-auto mb-3">
                <span className="font-mono text-data-lg text-telemetry-throttle">
                  ENG
                </span>
              </div>
              <p className="text-data-sm text-race-muted">
                Ask your race engineer anything
              </p>
              <p className="text-data-xs text-race-muted mt-1">
                Telemetry, strategy, lap analysis, historical data
              </p>
            </div>
          </div>
        )}

        {chatMessages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {isChatStreaming && <StreamingIndicator />}

        <div ref={messagesEndRef} />
      </div>

      {/* Quick-ask buttons */}
      <div className="px-3 py-1.5 border-t border-race-border flex gap-1.5 overflow-x-auto">
        {QUICK_ASKS.map((qa) => (
          <button
            key={qa.label}
            onClick={() => handleSubmit(qa.question)}
            disabled={isChatStreaming}
            className={clsx(
              "px-2 py-1 rounded border text-data-xs font-mono whitespace-nowrap transition-colors",
              isChatStreaming
                ? "border-race-border text-race-muted cursor-not-allowed"
                : "border-race-border text-race-muted hover:border-telemetry-speed/50 hover:text-telemetry-speed"
            )}
          >
            {qa.label}
          </button>
        ))}
      </div>

      {/* Input area */}
      <form
        onSubmit={onFormSubmit}
        className="px-3 py-2 border-t border-race-border flex gap-2"
      >
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask your race engineer..."
          disabled={isChatStreaming}
          className={clsx(
            "flex-1 bg-race-surface border border-race-border rounded-lg px-3 py-2",
            "text-data-sm font-sans text-race-text placeholder:text-race-muted",
            "focus:outline-none focus:border-telemetry-speed/50",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        />
        <button
          type="submit"
          disabled={!input.trim() || isChatStreaming}
          className={clsx(
            "px-4 py-2 rounded-lg font-mono text-data-sm transition-colors",
            input.trim() && !isChatStreaming
              ? "bg-telemetry-speed/20 text-telemetry-speed border border-telemetry-speed/30 hover:bg-telemetry-speed/30"
              : "bg-race-surface text-race-muted border border-race-border cursor-not-allowed"
          )}
        >
          SEND
        </button>
      </form>
    </div>
  );
}
