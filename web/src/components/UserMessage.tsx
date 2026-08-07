import "./UserMessage.css";

export function UserMessage({ text }: { text: string }) {
  return (
    <div className="ask">
      <span className="ask__label">You asked</span>
      <p className="ask__text">{text}</p>
    </div>
  );
}
