/** Number formatting shared by the tool cards and the turn footer, which sit
 * inches apart on screen: rounding them differently would be visible.
 */

/** `840ms`, `8.4s`, `2m 05s`. */
export function duration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

/** `830`, `12.4k`, `1.05M`. Exact below 1,000, where counts get compared. */
export function tokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

/** Four decimals: sub-cent turns are the common case. */
export function usd(value: number): string {
  if (value === 0) return "$0";
  if (value < 0.0001) return "<$0.0001";
  return `$${value.toFixed(4)}`;
}
