"use client";

import { use, useState, useRef, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Send, Loader2, MessageSquare, Bot, User, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { createInterview, askQuestionStream, getInterviewHistory } from "@/lib/api";
import type { InterviewMessage } from "@/lib/types";

const SUGGESTED_QUESTIONS = [
  "What is the root cause of the most critical issue?",
  "Which pods are in a crash loop and why?",
  "Are there any resource constraints causing problems?",
  "What should I fix first?",
  "Are there any security concerns in this bundle?",
  "Explain the timeline of failures",
];

export default function AskPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const bundleId = typeof id === "string" ? id : null;

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<InterviewMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleStart = useCallback(async () => {
    if (!bundleId) return;
    setStarting(true);
    try {
      const session = await createInterview(bundleId);
      setSessionId(session.session_id);
      const history = await getInterviewHistory(
        bundleId,
        session.session_id,
      );
      setMessages(history);
    } catch {
      // failed to start
    } finally {
      setStarting(false);
    }
  }, [bundleId]);

  const handleSend = useCallback(
    async (question: string) => {
      if (!bundleId || !sessionId || !question.trim()) return;

      const userMsg: InterviewMessage = {
        role: "user",
        content: question.trim(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setLoading(true);

      // Add a placeholder assistant message for streaming
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "" },
      ]);

      try {
        await askQuestionStream(
          bundleId,
          sessionId,
          question.trim(),
          (token) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + token,
                };
              }
              return updated;
            });
          },
          () => {
            setLoading(false);
          },
          (err) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  content:
                    "Sorry, I encountered an error processing your question. Please try again.",
                };
              }
              return updated;
            });
            setLoading(false);
          },
        );
      } catch {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              content:
                "Sorry, I encountered an error processing your question. Please try again.",
            };
          }
          return updated;
        });
        setLoading(false);
      }
    },
    [bundleId, sessionId],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend(input);
      }
    },
    [handleSend, input],
  );

  if (!bundleId) return null;

  // Not started yet
  if (!sessionId) {
    return (
      <div className="flex flex-col items-center justify-center gap-6 pt-32">
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ease: [0.22, 1, 0.36, 1] }}
          className="flex flex-col items-center gap-5"
        >
          <div
            className="flex h-14 w-14 items-center justify-center rounded-2xl"
            style={{ background: "var(--accent-gradient)", boxShadow: "0 0 30px rgba(99, 102, 241, 0.25)" }}
          >
            <MessageSquare size={24} color="white" />
          </div>
          <h2
            className="text-2xl font-bold"
            style={{ color: "var(--foreground-bright)" }}
          >
            Ask
          </h2>
          <p
            className="max-w-md text-center text-sm"
            style={{ color: "var(--muted)" }}
          >
            Start an ask session to ask questions about the
            analysis findings, timeline, and bundle contents.
          </p>
          <button
            onClick={handleStart}
            disabled={starting}
            className="btn-primary flex items-center gap-2"
          >
            {starting ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Sparkles size={16} />
            )}
            Start ask session
          </button>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-auto pb-4">
        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center gap-6 pt-16">
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              Ask a question about the bundle analysis
            </p>
            <div className="flex flex-wrap justify-center gap-2 max-w-2xl">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => handleSend(q)}
                  className="pill-btn"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-4">
          {messages.map((msg, i) => {
            // Skip rendering empty assistant message while loading dots are shown
            const isEmptyStreaming = msg.role === "assistant" && msg.content === "" && loading && i === messages.length - 1;
            if (isEmptyStreaming) return null;

            return (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {msg.role === "assistant" && (
                <div
                  className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl"
                  style={{ background: "var(--accent-gradient)" }}
                >
                  <Bot size={14} color="white" />
                </div>
              )}
              <div
                className={`max-w-2xl px-4 py-3 ${
                  msg.role === "user" ? "chat-user" : "chat-assistant"
                }`}
              >
                {msg.role === "assistant" ? (
                  <div className="prose-chat text-sm">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap text-sm">
                    {msg.content}
                  </p>
                )}
              </div>
              {msg.role === "user" && (
                <div
                  className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl"
                  style={{ background: "rgba(55, 65, 81, 0.5)" }}
                >
                  <User size={14} style={{ color: "var(--muted)" }} />
                </div>
              )}
            </motion.div>
            );
          })}

          {loading && messages.length > 0 && messages[messages.length - 1]?.content === "" && (
            <div className="flex items-center gap-3">
              <div
                className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl"
                style={{ background: "var(--accent-gradient)" }}
              >
                <Bot size={14} color="white" />
              </div>
              <div className="chat-assistant px-4 py-3">
                <div className="dot-pulse flex gap-1">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div
        className="flex items-end gap-3 border-t pt-4"
        style={{ borderColor: "var(--border-subtle)" }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about the bundle analysis..."
          rows={2}
          className="input-modern flex-1 resize-none p-3"
        />
        <button
          onClick={() => handleSend(input)}
          disabled={loading || !input.trim()}
          className="flex h-10 w-10 items-center justify-center rounded-xl transition-all hover:scale-105 disabled:opacity-40 disabled:hover:scale-100"
          style={{
            background: "var(--accent-gradient)",
            color: "white",
            boxShadow: "0 0 15px rgba(99, 102, 241, 0.2)",
          }}
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
