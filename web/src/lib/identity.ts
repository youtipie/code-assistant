const STORAGE_KEY = "assistant.client-id";

export function clientId(): string {
  const existing = window.localStorage.getItem(STORAGE_KEY);
  if (existing !== null && existing.length > 0) return existing;
  const created = crypto.randomUUID();
  window.localStorage.setItem(STORAGE_KEY, created);
  return created;
}
