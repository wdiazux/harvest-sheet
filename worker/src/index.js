import { verifyGoogleToken, googleJWKS } from "./google.js";
import { isAllowed } from "./allowlist.js";
import { validateInputs } from "./validate.js";
import { mintInstallationToken, dispatchWorkflow } from "./github.js";

function cors(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
  };
}
const json = (env, status, obj) =>
  new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...cors(env) } });

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(env) });
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/trigger") return json(env, 404, { error: "not found" });

    if (env.RATE_LIMITER) {
      const ip = request.headers.get("cf-connecting-ip") || "unknown";
      const { success } = await env.RATE_LIMITER.limit({ key: ip });
      if (!success) return json(env, 429, { error: "rate limited" });
    }

    let body;
    try { body = await request.json(); } catch { return json(env, 400, { error: "bad json" }); }

    const auth = await verifyGoogleToken(body.google_id_token, env.GOOGLE_CLIENT_ID, googleJWKS());
    if (!auth.ok) return json(env, 401, { error: "unauthenticated" });
    if (!isAllowed(auth.email, env.ALLOWED_EMAILS)) return json(env, 403, { error: "forbidden" });

    const { ok, value } = validateInputs(body);
    if (!ok) return json(env, 400, { error: "invalid input" });

    const token = await mintInstallationToken(env);
    if (!token) return json(env, 502, { error: "upstream auth failed" });

    const dispatched = await dispatchWorkflow(env, token, value);
    if (!dispatched) return json(env, 502, { error: "dispatch failed" });

    return json(env, 202, { status: "triggered" });
  },
};
