const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const PREFIX_RE = /^[A-Za-z0-9_]+$/;

export function validateInputs(body) {
  const from_date = String(body?.from_date ?? "");
  const to_date = String(body?.to_date ?? "");
  if (!DATE_RE.test(from_date) || !DATE_RE.test(to_date)) return { ok: false };

  let user_prefix = body?.user_prefix ? String(body.user_prefix) : "all";
  if (user_prefix !== "all" && !PREFIX_RE.test(user_prefix)) return { ok: false };

  return {
    ok: true,
    value: {
      from_date,
      to_date,
      user_prefix,
      upload_to_sheets: body?.upload_to_sheets ? "true" : "false",
      include_advanced_fields: body?.include_advanced_fields ? "true" : "false",
    },
  };
}
