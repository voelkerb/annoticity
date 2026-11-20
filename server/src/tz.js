const formatters = new Map();

function formatter(tz) {
  let f = formatters.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", {
      timeZone: tz, hourCycle: "h23",
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    formatters.set(tz, f);
  }
  return f;
}

function localParts(epochSec, tz) {
  const parts = {};
  for (const p of formatter(tz).formatToParts(new Date(epochSec * 1000))) parts[p.type] = p.value;
  return {
    year: +parts.year, month: +parts.month, day: +parts.day,
    hour: +parts.hour, minute: +parts.minute, second: +parts.second,
  };
}

/** Offset of `tz` to UTC in seconds at the given instant. */
export function tzOffset(epochSec, tz) {
  const p = localParts(epochSec, tz);
  return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) / 1000 - Math.floor(epochSec);
}

/** Epoch seconds of local midnight of "YYYY-MM-DD" in `tz`. */
export function zonedDayStart(ymd, tz) {
  const [y, m, d] = ymd.split("-").map(Number);
  const utcGuess = Date.UTC(y, m - 1, d) / 1000;
  let t = utcGuess - tzOffset(utcGuess, tz);
  t = utcGuess - tzOffset(t, tz);
  return t;
}

/** Local time formatted like the FIRED file names: YYYY_MM_DD__HH_MM_SS */
export function fileStamp(epochSec, tz) {
  const p = localParts(epochSec, tz);
  const z = (n) => String(n).padStart(2, "0");
  return `${p.year}_${z(p.month)}_${z(p.day)}__${z(p.hour)}_${z(p.minute)}_${z(p.second)}`;
}
