// All times are shown in India Standard Time, whatever the viewer's device clock is set to.
const IST = 'Asia/Kolkata';

/** Parse a server timestamp. Older records carry no offset; they are UTC, so say so. */
export function parseServerTime(value: string | number): Date {
  if (typeof value === 'number') return new Date(value * 1000);
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value);
  return new Date(hasZone ? value : `${value}Z`);
}

/** e.g. "2 Oct 2026, 3:45 pm IST" */
export function formatIST(value: string | number): string {
  return parseServerTime(value).toLocaleString('en-IN', {
    timeZone: IST, day: 'numeric', month: 'short', year: 'numeric',
    hour: 'numeric', minute: '2-digit', hour12: true,
  }) + ' IST';
}

/** e.g. "2 Oct 2026" */
export function formatDateIST(value: string | number): string {
  return parseServerTime(value).toLocaleDateString('en-IN', {
    timeZone: IST, day: 'numeric', month: 'short', year: 'numeric',
  });
}

/** Instagram-style: "just now", "5m", "3h", "2d", then the IST date. */
export function timeAgo(value: string | number): string {
  const date = parseServerTime(value);
  const diff = Math.max(0, (Date.now() - date.getTime()) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 7 * 86400) return `${Math.floor(diff / 86400)}d ago`;
  return date.toLocaleDateString('en-IN', { timeZone: IST, day: 'numeric', month: 'long', year: 'numeric' });
}
