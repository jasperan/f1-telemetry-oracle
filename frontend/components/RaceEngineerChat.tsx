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
import { useStore, ChatMessage, RetrievalTrace } from "@/lib/store";

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
        "flex gap-2.5 animate-fade-in-up",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <div
        className={clsx(
          "w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 text-data-xs font-mono font-semibold",
          isUser
            ? "bg-accent-primary/12 text-accent-primary border border-accent-primary/15"
            : isSystem
              ? "bg-race-border/40 text-race-muted border border-race-border/30"
              : "bg-accent-positive/12 text-accent-positive border border-accent-positive/15"
        )}
      >
        {isUser ? "DRV" : isSystem ? "SYS" : "ENG"}
      </div>

      {/* Message content */}
      <div
        className={clsx(
          "max-w-[85%] rounded-xl px-3.5 py-2.5",
          isUser
            ? "bg-accent-primary/8 border border-accent-primary/15"
            : isSystem
              ? "bg-race-surface/80 border border-race-border/40"
              : "bg-race-card/80 border border-race-border/40"
        )}
      >
        {isUser ? (
          <p className="text-data-sm text-race-text">{message.content}</p>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none">
            <ReactMarkdown
              components={{
                p: ({ children }) => (
                  <p className="text-data-sm text-race-text/90 mb-2 last:mb-0 leading-relaxed">
                    {children}
                  </p>
                ),
                strong: ({ children }) => (
                  <strong className="text-accent-primary font-mono font-semibold">
                    {children}
                  </strong>
                ),
                li: ({ children }) => (
                  <li className="text-data-sm text-race-text/90 ml-4 list-disc leading-relaxed">
                    {children}
                  </li>
                ),
                code: ({ children }) => (
                  <code className="font-mono text-data-xs bg-race-surface/80 px-1.5 py-0.5 rounded-md text-accent-purple">
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
          <div className="flex items-center gap-2 mt-2 pt-1.5 border-t border-race-border/30">
            <span className="text-data-xs font-mono text-race-muted/60">
              {message.intent}
            </span>
            {message.sources && (
              <span className="text-data-xs font-mono text-race-muted/40">
                {Object.entries(message.sources)
                  .filter(([, v]) => v > 0)
                  .map(([k, v]) => `${k}:${v}`)
                  .join(" ")}
              </span>
            )}
            {message.elapsed_ms !== undefined && (
              <span className="text-data-xs font-mono text-race-muted/50 ml-auto">
                {message.elapsed_ms}ms
              </span>
            )}
          </div>
        )}

        {/* Retrieval trace (transparency panel) */}
        {message.trace && !isUser && (
          <div className="mt-2 pt-1.5 border-t border-race-border/30 space-y-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span
                className={clsx(
                  "text-[0.55rem] font-mono px-1.5 py-0.5 rounded tracking-wider font-semibold",
                  message.trace.path === "agent"
                    ? "bg-accent-purple/12 text-accent-purple border border-accent-purple/20"
                    : "bg-accent-primary/12 text-accent-primary border border-accent-primary/20"
                )}
              >
                {message.trace.path === "agent" ? "AGENT" : "RAG"}
              </span>
              {message.trace.tool_calls && message.trace.tool_calls.length > 0 && (
                <span className="text-data-xs font-mono text-accent-purple/80">
                  tools: {message.trace.tool_calls.join(" → ")}
                </span>
              )}
              {message.trace.iterations !== undefined &&
                message.trace.iterations > 0 && (
                  <span className="text-data-xs font-mono text-race-muted/50">
                    {message.trace.iterations} iter
                  </span>
                )}
              {message.trace.stages_ms &&
                Object.keys(message.trace.stages_ms).length > 0 && (
                  <span className="text-data-xs font-mono text-race-muted/40 ml-auto">
                    {Object.entries(message.trace.stages_ms)
                      .map(([k, v]) => `${k.replace("_ms", "")}:${v}ms`)
                      .join(" ")}
                  </span>
                )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Streaming indicator dots. */
function StreamingIndicator() {
  return (
    <div className="flex gap-2.5 items-start animate-fade-in">
      <div className="w-7 h-7 rounded-lg bg-accent-positive/12 flex items-center justify-center flex-shrink-0 border border-accent-positive/15">
        <span className="text-data-xs font-mono font-semibold text-accent-positive">
          ENG
        </span>
      </div>
      <div className="bg-race-card/80 border border-race-border/40 rounded-xl px-3.5 py-3">
        <div className="flex gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-accent-positive/60 animate-bounce [animation-delay:0ms]" />
          <div className="w-1.5 h-1.5 rounded-full bg-accent-positive/60 animate-bounce [animation-delay:150ms]" />
          <div className="w-1.5 h-1.5 rounded-full bg-accent-positive/60 animate-bounce [animation-delay:300ms]" />
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
              last.trace = msg.trace as RetrievalTrace;
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
    <article className="panel h-full flex flex-col">
      <div className="panel-header">
        <div className="flex items-center gap-2.5">
          <span className="panel-title">Race engineer</span>
          <span
            className={clsx(
              "text-[0.6rem] font-mono px-2 py-0.5 rounded-md tracking-wider font-medium transition-colors duration-300",
              wsState === "connected"
                ? "bg-accent-positive/10 text-accent-positive border border-accent-positive/15"
                : "bg-accent-negative/10 text-accent-negative border border-accent-negative/15"
            )}
          >
            {wsState === "connected" ? "LIVE" : "OFFLINE"}
          </span>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-3.5 flex flex-col gap-3 min-h-0">
        {chatMessages.length === 0 && (
          <div className="flex-1 flex items-center justify-center text-center animate-fade-in">
            <div>
              <div className="w-12 h-12 rounded-xl bg-accent-positive/8 flex items-center justify-center mx-auto mb-3 border border-accent-positive/10">
                <span className="font-mono text-data-lg text-accent-positive font-semibold">
                  ENG
                </span>
              </div>
              <p className="text-data-sm text-race-text-secondary font-medium">
                Ask your race engineer anything
              </p>
              <p className="text-data-xs text-race-muted/50 mt-1.5">
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
      <div className="px-3.5 py-2 border-t border-race-border/30 flex gap-1.5 overflow-x-auto">
        {QUICK_ASKS.map((qa) => (
          <button
            key={qa.label}
            onClick={() => handleSubmit(qa.question)}
            disabled={isChatStreaming}
            className="pill-btn"
          >
            {qa.label}
          </button>
        ))}
      </div>

      {/* Input area */}
      <form
        onSubmit={onFormSubmit}
        className="px-3.5 py-2.5 border-t border-race-border/30 flex gap-2"
      >
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask your race engineer..."
          disabled={isChatStreaming}
          className="input-field flex-1"
          aria-label="Chat message input"
        />
        <button
          type="submit"
          disabled={!input.trim() || isChatStreaming}
          className="btn-primary"
          aria-label="Send message"
        >
          Send
        </button>
      </form>
    </article>
  );
}
