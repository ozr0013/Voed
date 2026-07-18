// mm:ss(.d) time formatting for the timeline and clip labels.
export function fmtTime(s: number, withTenths = false): string {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (withTenths) {
    return `${m}:${sec.toFixed(1).padStart(4, "0")}`;
  }
  return `${m}:${Math.floor(sec).toString().padStart(2, "0")}`;
}
