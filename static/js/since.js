// The time since a date, counted to the device's today, in the page's language.

// A date as the device sees it, in the form date inputs and <time datetime> use.
export function localDate(date = new Date()) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function parts(isoDate) {
  return isoDate.split("-").map(Number);
}

// A date as the pages write it, day, month and year, such as "1 September 2026".
export function formatDate(isoDate, language) {
  const [year, month, day] = parts(isoDate);
  const format = new Intl.DateTimeFormat(language, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  const named = Object.fromEntries(
    format.formatToParts(new Date(Date.UTC(year, month - 1, day))).map(({ type, value }) => [type, value]),
  );
  return `${named.day} ${named.month} ${named.year}`;
}

function daysBetween(from, to) {
  const [fromYear, fromMonth, fromDay] = parts(from);
  const [toYear, toMonth, toDay] = parts(to);
  return Math.round((Date.UTC(toYear, toMonth - 1, toDay) - Date.UTC(fromYear, fromMonth - 1, fromDay)) / 86_400_000);
}

// Whole calendar months: 31 January to 28 February is not yet a month.
function monthsBetween(from, to) {
  const [fromYear, fromMonth, fromDay] = parts(from);
  const [toYear, toMonth, toDay] = parts(to);
  return (toYear - fromYear) * 12 + (toMonth - fromMonth) - (toDay < fromDay ? 1 : 0);
}

// A date entered on a device a day ahead of this one counts as today.
function daysSince(from, to) {
  return Math.max(0, daysBetween(from, to));
}

// The time since in the unit a person would answer with: days up to two weeks, weeks up to two whole months,
// months up to two years, then years.
export function naturalAmount(from, to) {
  const days = daysSince(from, to);
  const months = Math.max(0, monthsBetween(from, to));
  if (days < 14) {
    return [days, "day"];
  }
  if (months < 2) {
    return [Math.floor(days / 7), "week"];
  }
  if (months < 24) {
    return [months, "month"];
  }
  return [Math.floor(months / 12), "year"];
}

// In days, or in the natural unit.
export function describeSince(from, to, unit, language) {
  const [count, name] = unit === "natural" ? naturalAmount(from, to) : [daysSince(from, to), "day"];
  return new Intl.NumberFormat(language, { style: "unit", unit: name, unitDisplay: "long" }).format(count);
}
