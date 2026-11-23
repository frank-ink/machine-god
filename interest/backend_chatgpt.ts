// ChatGPT bridge backend (isolated). Needs MG_CHATGPT_BRIDGE_URL; token in MG_CHATGPT_BRIDGE_TOKEN.
// Contract: POST {url}/chatgpt/send  {prompt, timeout_s}  -> JSON with text in text|reply|response|result, or plain text.
export async function send(prompt: string, timeoutS = 120): Promise<string> {
  const url = process.env.MG_CHATGPT_BRIDGE_URL;
  if (!url) throw new Error("MG_CHATGPT_BRIDGE_URL not set");
  const token = process.env.MG_CHATGPT_BRIDGE_TOKEN;
  const res = await fetch(url.replace(/\/+$/, "") + "/chatgpt/send", {
    method: "POST",
    headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify({ prompt, timeout_s: timeoutS }),
    signal: AbortSignal.timeout((timeoutS + 10) * 1000),
  });
  const body = await res.text();
  if (!res.ok) throw new Error(`bridge HTTP ${res.status}`);
  try {
    const j = JSON.parse(body);
    for (const k of ["text", "reply", "response", "result"]) if (typeof j?.[k] === "string") return j[k];
  } catch {}
  return body;
}
