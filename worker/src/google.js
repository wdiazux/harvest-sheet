import { jwtVerify, createRemoteJWKSet } from "jose";

const GOOGLE_ISSUERS = ["https://accounts.google.com", "accounts.google.com"];

// Production resolver (cached by jose). Tests inject their own resolver.
export function googleJWKS() {
  return createRemoteJWKSet(new URL("https://www.googleapis.com/oauth2/v3/certs"));
}

export async function verifyGoogleToken(idToken, clientId, jwksResolver) {
  try {
    const { payload } = await jwtVerify(idToken, jwksResolver, {
      audience: clientId,
      issuer: GOOGLE_ISSUERS,
    });
    if (payload.email_verified !== true) return { ok: false };
    if (!payload.email) return { ok: false };
    return { ok: true, email: String(payload.email) };
  } catch {
    return { ok: false };
  }
}
