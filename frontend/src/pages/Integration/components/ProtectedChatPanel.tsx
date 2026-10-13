import { AlertTriangle, CheckCircle2, LoaderCircle, Play, ShieldCheck, Square } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import type { FormEvent } from "react"

import { useAuth } from "../../../hooks/useAuth"
import {
  fetchProtectedChatReadiness,
  submitProtectedChat,
  type ProtectedChatReadiness,
  type ProtectedChatResponse,
  type ProtectedChatStatus,
} from "../../../services/protectedChatService"

type PanelState = ProtectedChatStatus | "idle" | "loading" | "cancelled"

const stateCopy: Record<ProtectedChatStatus, { title: string; tone: string }> = {
  allowed: { title: "Allowed by enabled checks", tone: "text-brand-green" },
  redacted: { title: "Redacted response returned", tone: "text-brand-green" },
  blocked: { title: "Request blocked", tone: "text-brand-red" },
  evaluation_failed: { title: "Safety check incomplete", tone: "text-brand-red" },
  provider_unavailable: { title: "Provider unavailable", tone: "text-brand-red" },
  service_unavailable: { title: "Protected demo unavailable", tone: "text-brand-red" },
  busy: { title: "Request already in progress", tone: "text-text-muted" },
}

function resultMessage(result: ProtectedChatResponse): string {
  switch (result.status) {
    case "allowed":
      return "No enabled rule blocked this request."
    case "redacted":
      return "Sensitive content was removed before the answer was returned."
    case "blocked":
      return "A guardrail stopped this request. No model answer was returned."
    case "evaluation_failed":
      return "A safety check could not complete. The request was stopped safely."
    case "provider_unavailable":
      return "The configured model provider is unavailable. No answer was returned."
    case "service_unavailable":
      return "The protected demo could not complete safely. No answer was returned."
    case "busy":
      return "Another protected request is already running for this account."
  }
}

function ProtectedChatPanel() {
  const { isAuthenticated, isHydrated, isLoading: authLoading, user } = useAuth()
  const [message, setMessage] = useState("")
  const [readiness, setReadiness] = useState<ProtectedChatReadiness | null>(null)
  const [readinessError, setReadinessError] = useState(false)
  const [panelState, setPanelState] = useState<PanelState>("idle")
  const [result, setResult] = useState<ProtectedChatResponse | null>(null)
  const activeRequest = useRef<AbortController | null>(null)
  const sessionKey = isAuthenticated ? user?.id ?? null : null
  const sessionKeyRef = useRef<string | null>(sessionKey)
  const previousSessionKey = useRef<string | null>(sessionKey)
  sessionKeyRef.current = sessionKey

  useEffect(() => {
    if (previousSessionKey.current === sessionKey) return

    previousSessionKey.current = sessionKey
    activeRequest.current?.abort()
    activeRequest.current = null
    setPanelState("idle")
    setResult(null)
    setReadiness(null)
    setReadinessError(false)
  }, [sessionKey])

  useEffect(() => {

    if (!isHydrated || authLoading || !sessionKey) {
      setReadiness(null)
      setReadinessError(false)
      return
    }

    const controller = new AbortController()
    const requestSession = sessionKey
    void fetchProtectedChatReadiness(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted && sessionKeyRef.current === requestSession) {
          setReadiness(value)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted && sessionKeyRef.current === requestSession) {
          setReadinessError(true)
        }
      })

    return () => {
      controller.abort()
    }
  }, [authLoading, isHydrated, sessionKey])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = message.trim()
    if (!trimmed || panelState === "loading" || activeRequest.current || !sessionKeyRef.current) return

    const requestSession = sessionKeyRef.current
    const controller = new AbortController()
    activeRequest.current = controller
    setPanelState("loading")
    setResult(null)

    try {
      const response = await submitProtectedChat(trimmed, controller.signal)
      if (controller.signal.aborted || sessionKeyRef.current !== requestSession) return
      setResult(response)
      setPanelState(response.status)
    } catch {
      if (controller.signal.aborted || sessionKeyRef.current !== requestSession) return
      setPanelState("service_unavailable")
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null
        if (!controller.signal.aborted && sessionKeyRef.current === requestSession) {
          setPanelState((current) => current === "loading" ? "idle" : current)
        }
      }
    }
  }

  function cancelRequest() {
    activeRequest.current?.abort()
    activeRequest.current = null
    setPanelState("cancelled")
    setResult(null)
  }

  const isBusy = panelState === "loading"
  const copy = result ? stateCopy[result.status] : null

  return (
    <section className="bg-card-bg border border-border-color rounded-2xl p-5 sm:p-6 space-y-4" aria-labelledby="protected-chat-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-brand-green" aria-hidden="true" />
            <h2 id="protected-chat-title" className="text-lg font-semibold">Try a protected request</h2>
          </div>
          <p className="mt-1 text-sm text-text-muted">
            The sample uses your current Protection settings and policies before returning an answer.
          </p>
        </div>
        <span className={`inline-flex items-center gap-2 rounded-full border border-border-color px-3 py-1 text-xs ${readiness?.ready ? "text-brand-green" : "text-text-muted"}`}>
          {readiness?.ready ? <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> : <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />}
          {readiness?.ready ? "Provider ready" : "Provider not ready"}
        </span>
      </div>

      <p className="text-xs text-text-muted">
        Use synthetic examples, not real personal data. Attempts are recorded in Activity History; stop-waiting may not cancel work already running on the server.
      </p>
      <p className="text-xs text-text-muted">
        Only checks enabled in Protection and Policies are applied. An allowed result is not a guarantee that a message is safe.
      </p>

      {readinessError ? (
        <p className="rounded-lg border border-brand-red/30 bg-brand-red/10 px-3 py-2 text-sm text-brand-red" role="status">
          Setup status could not be loaded. Requests still stop safely if a check or provider is unavailable.
        </p>
      ) : readiness && !readiness.ready ? (
        <p className="rounded-lg border border-border-color bg-dashboard-bg px-3 py-2 text-sm text-text-muted" role="status">
          Backend setup is incomplete ({readiness.error_code ?? "provider_unavailable"}). Local guardrails still run; requests that need generation fail safely.
        </p>
      ) : null}

      <form onSubmit={(event) => void handleSubmit(event)} className="space-y-3">
        <label htmlFor="protected-chat-message" className="block text-sm font-medium">Message</label>
        <textarea
          id="protected-chat-message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          maxLength={8000}
          rows={4}
          disabled={isBusy}
          placeholder="Example: Please summarize the launch checklist."
          className="w-full resize-y rounded-xl border border-border-color bg-dashboard-bg px-3 py-3 text-sm text-white placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-brand-green/60 disabled:opacity-60"
          aria-describedby="protected-chat-help"
          data-testid="protected-chat-message"
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p id="protected-chat-help" className="text-xs text-text-muted">Maximum 8,000 characters.</p>
          <div className="flex items-center gap-2">
            {isBusy ? (
              <button
                type="button"
                onClick={cancelRequest}
                className="inline-flex items-center gap-2 rounded-lg border border-border-color px-4 py-2 text-sm hover:bg-white/5"
                data-testid="protected-chat-stop-waiting"
              >
                <Square className="h-3.5 w-3.5" aria-hidden="true" /> Stop waiting
              </button>
            ) : null}
            <button
              type="submit"
              disabled={!message.trim() || isBusy || !isAuthenticated || authLoading}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-green px-4 py-2 text-sm font-semibold text-slate-950 hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="protected-chat-submit"
            >
              {isBusy ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}
              {isBusy ? "Checking…" : "Run protected request"}
            </button>
          </div>
        </div>
      </form>

      <div className="min-h-6 text-sm" role="status" aria-live="polite" aria-atomic="true" data-testid="protected-chat-status">
        {isBusy ? (
          <span className="inline-flex items-center gap-2 text-text-muted"><LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" /> Running checks and waiting for a protected response…</span>
        ) : copy ? (
          <span className={copy.tone}>{copy.title}: {resultMessage(result!)}</span>
        ) : panelState === "service_unavailable" ? (
          <span className="text-brand-red">The service could not be reached. No answer was returned.</span>
        ) : panelState === "cancelled" ? (
          <span className="text-text-muted">Stopped waiting. Server-side processing may continue; check Activity History before retrying.</span>
        ) : null}
      </div>

      {result ? (
        <div className="rounded-xl border border-border-color bg-dashboard-bg p-4 space-y-3" data-testid="protected-chat-result">
          {result.answer ? (
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-text-muted">Protected response</p>
              <p className="whitespace-pre-wrap break-words text-sm">{result.answer}</p>
            </div>
          ) : result.fallback_message ? (
            <p className="whitespace-pre-wrap break-words text-sm text-text-muted">{result.fallback_message}</p>
          ) : null}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
            <span>Policy version {result.policy_version}</span>
            <span>{result.audit_ids.length} audit {result.audit_ids.length === 1 ? "record" : "records"} saved</span>
            {result.input_redacted ? <span>Input redacted</span> : null}
            {result.output_redacted ? <span>Output redacted</span> : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}

export default ProtectedChatPanel
