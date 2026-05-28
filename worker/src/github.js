import { SignJWT, importPKCS8 } from "jose";

const API = "https://api.github.com";
const UA = "harvest-web-trigger";

// env.GH_APP_PRIVATE_KEY must be PKCS8 PEM ("BEGIN PRIVATE KEY").
export async function mintInstallationToken(env) {
  const key = await importPKCS8(env.GH_APP_PRIVATE_KEY, "RS256");
  const now = Math.floor(Date.now() / 1000);
  const appJwt = await new SignJWT({})
    .setProtectedHeader({ alg: "RS256" })
    .setIssuedAt(now - 60)
    .setExpirationTime(now + 600)
    .setIssuer(String(env.GH_APP_ID))
    .sign(key);

  const res = await fetch(`${API}/app/installations/${env.GH_APP_INSTALLATION_ID}/access_tokens`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${appJwt}`,
      Accept: "application/vnd.github+json",
      "User-Agent": UA,
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.token ?? null;
}

export async function dispatchWorkflow(env, installationToken, inputs) {
  const url = `${API}/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${env.WORKFLOW_FILE}/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${installationToken}`,
      Accept: "application/vnd.github+json",
      "User-Agent": UA,
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: env.WORKFLOW_REF, inputs }),
  });
  return res.status === 204;
}
