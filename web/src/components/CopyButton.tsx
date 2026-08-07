import { useState } from "react";
import "./CopyButton.css";


export function CopyButton({ text, label = "Copy raw" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      type="button"
      className="copy"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          window.setTimeout(() => {
            setCopied(false);
          }, 1500);
        });
      }}
    >
      {copied ? "Copied" : label}
    </button>
  );
}
