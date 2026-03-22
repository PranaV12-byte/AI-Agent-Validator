import { Check, Copy, KeyRound } from "lucide-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { useAuth } from "../../hooks/useAuth"

type SnippetCardProps = {
  title: string
  code: string
  testId: string
  onCopy: (value: string) => Promise<void>
}

function SnippetCard({ title, code, testId, onCopy }: SnippetCardProps) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    await onCopy(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }

  return (
    <article className="bg-card-bg border border-border-color rounded-2xl p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">{title}</h2>
        <button
          type="button"
          onClick={() => void handleCopy()}
          className="inline-flex items-center gap-2 rounded-lg border border-border-color px-3 py-2 text-sm text-text-muted hover:text-white hover:bg-white/5 transition-colors"
          data-testid={`${testId}-copy`}
        >
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre
        className="bg-dashboard-bg border border-border-color rounded-xl p-4 text-xs leading-6 overflow-x-auto"
        data-testid={`${testId}-code`}
      >
        <code>{code}</code>
      </pre>
    </article>
  )
}

async function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  const textarea = document.createElement("textarea")
  textarea.value = text
  textarea.style.position = "fixed"
  textarea.style.opacity = "0"
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()

  const copied = document.execCommand("copy")
  document.body.removeChild(textarea)
  if (!copied) {
    throw new Error("Clipboard copy failed")
  }
}

function IntegrationPage() {
  const { user } = useAuth()

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"

  const curlSnippet = useMemo(
    () => `API_BASE_URL="${apiBaseUrl}"
SAFEBOT_API_KEY="sk-REPLACE_WITH_FULL_KEY"

curl -sS -X POST "$API_BASE_URL/validate" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: $SAFEBOT_API_KEY" \\
  -d '{"prompt":"My email is alice@example.com","user_id":"sdk-user-1"}'

# If you receive HTTP 429, retry with exponential backoff.
# Respect Retry-After when present before retrying.`,
    [apiBaseUrl],
  )

  const pythonSnippet = useMemo(
    () => `import os
import time
import requests

api_base_url = os.getenv("API_BASE_URL", "${apiBaseUrl}")
api_key = os.getenv("SAFEBOT_API_KEY", "sk-REPLACE_WITH_FULL_KEY")

payload = {"prompt": "My email is alice@example.com", "user_id": "sdk-user-1"}
headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

for attempt in range(5):
    response = requests.post(f"{api_base_url}/validate", json=payload, headers=headers, timeout=10)
    if response.status_code != 429:
        print(response.status_code, response.json())
        break

    retry_after = int(response.headers.get("Retry-After", "1"))
    sleep_for = max(retry_after, 2 ** attempt)
    print(f"Rate limited (429). Retrying in {sleep_for}s...")
    time.sleep(sleep_for)`,
    [apiBaseUrl],
  )

  const nodeSnippet = useMemo(
    () => `const apiBaseUrl = process.env.API_BASE_URL || "${apiBaseUrl}";
const apiKey = process.env.SAFEBOT_API_KEY || "sk-REPLACE_WITH_FULL_KEY";

const payload = { prompt: "My email is alice@example.com", user_id: "sdk-user-1" };

for (let attempt = 0; attempt < 5; attempt += 1) {
  const response = await fetch(apiBaseUrl + "/validate", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify(payload),
  });

  if (response.status !== 429) {
    console.log(response.status, await response.json());
    break;
  }

  const retryAfter = Number(response.headers.get("retry-after") || "1");
  const sleepFor = Math.max(retryAfter * 1000, 2 ** attempt * 1000);
  console.log("Rate limited (429). Retrying in " + sleepFor / 1000 + "s...");
  await new Promise((resolve) => setTimeout(resolve, sleepFor));
}`,
    [apiBaseUrl],
  )

  async function handleCopy(code: string) {
    try {
      await copyToClipboard(code)
      toast.success("Snippet copied")
    } catch {
      toast.error("Could not copy snippet")
    }
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-2">Integration</h1>
        <p className="text-text-muted">Use these snippets to call the Safebot validation API from your backend.</p>
      </div>

      <div className="rounded-2xl border border-brand-green/30 bg-brand-green/10 px-4 py-3 inline-flex items-center gap-3">
        <KeyRound className="h-4 w-4 text-brand-green" />
        <p className="text-sm">
          API key prefix: <span className="font-mono text-brand-green">{user?.api_key_prefix ?? "--"}</span>
        </p>
      </div>

      <SnippetCard title="cURL" code={curlSnippet} testId="snippet-curl" onCopy={handleCopy} />
      <SnippetCard
        title="Python (requests)"
        code={pythonSnippet}
        testId="snippet-python"
        onCopy={handleCopy}
      />
      <SnippetCard
        title="Node.js (fetch)"
        code={nodeSnippet}
        testId="snippet-node"
        onCopy={handleCopy}
      />
    </section>
  )
}

export default IntegrationPage
