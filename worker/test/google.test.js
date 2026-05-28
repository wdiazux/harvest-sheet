import { describe, it, expect, beforeAll } from "vitest";
import { generateKeyPair, exportJWK, SignJWT } from "jose";
import { verifyGoogleToken } from "../src/google.js";

const CLIENT_ID = "test-client-id.apps.googleusercontent.com";
let privateKey, jwks;

beforeAll(async () => {
  const kp = await generateKeyPair("RS256");
  privateKey = kp.privateKey;
  const pub = await exportJWK(kp.publicKey);
  pub.kid = "test-kid"; pub.alg = "RS256";
  jwks = async () => kp.publicKey; // resolver stub
});

async function mint(claims) {
  return await new SignJWT(claims)
    .setProtectedHeader({ alg: "RS256", kid: "test-kid" })
    .setIssuer("https://accounts.google.com")
    .setAudience(CLIENT_ID)
    .setIssuedAt()
    .setExpirationTime("5m")
    .sign(privateKey);
}

describe("verifyGoogleToken", () => {
  it("returns email for a valid, verified token", async () => {
    const token = await mint({ email: "alice@example.com", email_verified: true });
    const { ok, email } = await verifyGoogleToken(token, CLIENT_ID, jwks);
    expect(ok).toBe(true);
    expect(email).toBe("alice@example.com");
  });
  it("rejects wrong audience", async () => {
    const token = await mint({ email: "a@e.com", email_verified: true, aud: "other" });
    const { ok } = await verifyGoogleToken(token, "different-client", jwks);
    expect(ok).toBe(false);
  });
  it("rejects email_verified=false", async () => {
    const token = await mint({ email: "a@e.com", email_verified: false });
    const { ok } = await verifyGoogleToken(token, CLIENT_ID, jwks);
    expect(ok).toBe(false);
  });
});
