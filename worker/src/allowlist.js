export function isAllowed(email, allowedCsv) {
  if (!email || !allowedCsv) return false;
  const target = String(email).trim().toLowerCase();
  return String(allowedCsv)
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean)
    .includes(target);
}
