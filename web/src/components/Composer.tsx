import { useEffect, useRef, useState } from "react";
import "./Composer.css";

interface Props {
  onSend: (text: string) => void;
  onCancel: () => void;
  busy: boolean;
  disabled: boolean;
}

export function Composer({ onSend, onCancel, busy, disabled }: Props) {
  const [value, setValue] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!busy) field.current?.focus();
  }, [busy]);

  useEffect(() => {
    const element = field.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 220)}px`;
  }, [value]);

  const submit = () => {
    const text = value.trim();
    if (!text || busy || disabled) return;
    onSend(text);
    setValue("");
  };

  return (
    <div className="composer">
      <textarea
        ref={field}
        className="composer__field"
        rows={1}
        value={value}
        placeholder={disabled ? "Reconnecting…" : "Ask about the codebase"}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
        aria-label="Ask about the codebase"
      />
      {busy ? (
        <button type="button" className="composer__action composer__action--stop" onClick={onCancel}>
          Stop
        </button>
      ) : (
        <button
          type="button"
          className="composer__action"
          onClick={submit}
          disabled={disabled || value.trim().length === 0}
        >
          Ask
        </button>
      )}
    </div>
  );
}
