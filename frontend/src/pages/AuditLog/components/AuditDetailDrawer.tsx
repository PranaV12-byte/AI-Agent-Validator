import { useEffect, useRef, useState } from "react"
import { X } from "lucide-react"

import { useNativeModalDialog } from "../../../hooks/useNativeModalDialog"
import { getErrorMessage } from "../../../services/apiClient"
import { fetchDecisionFeedback, saveDecisionFeedback } from "../../../services/testLabService"
import type { AuditLog, DecisionFeedback, ExpectedTestAction } from "../../../types/api"

type ReviewDecision = "correct" | "incorrect" | "unsure"
type ReviewStatus = "open" | "resolved"

type AuditDetailDrawerProps = {
  log: AuditLog | null
  onClose: () => void
  onCreateTest?: (draft: { sourceFeedbackId: string; expectedAction?: ExpectedTestAction; name: string }) => void
  onFeedbackSaved?: () => void
}

function inferReason(log: AuditLog): string {
  if (log.action === "BLOCKED") return log.violation_type ?? "Blocked by policy"
  if (log.action === "REDACTED") return log.violation_type ?? "Sensitive data redacted"
  if (log.action === "ERROR") return log.violation_type ?? "Request could not be completed"
  return "Request allowed by guardrails"
}

function actionLabel(action: AuditLog["action"]): string {
  return action === "ERROR" ? "ERROR" : action.toLowerCase()
}

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString()
}

function getAnchoringStatus(log: AuditLog): NonNullable<AuditLog["anchoring_status"]> {
  const transactionId = log.algorand_tx_id
  if (transactionId?.toLowerCase().startsWith("mock_tx_")) {
    return "not_anchored"
  }
  if (log.anchoring_status === "anchored" && !transactionId) {
    return "pending"
  }
  if (log.anchoring_status) {
    return log.anchoring_status
  }
  return transactionId ? "anchored" : "pending"
}

function anchoringLabel(status: NonNullable<AuditLog["anchoring_status"]>): string {
  switch (status) {
    case "anchored": return "Anchored"
    case "pending": return "Pending"
    case "disabled": return "Disabled for this local demo"
    case "not_anchored": return "Not anchored"
  }
}

function hashProvenanceLabel(log: AuditLog): string {
  if (log.payload_hash_provenance === "stored_unverified") {
    return "Stored hash; not independently verified"
  }
  if (log.payload_hash_provenance === "unavailable" || !log.payload_hash) {
    return "Unavailable"
  }
  return "Stored hash; provenance not supplied"
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-text-muted mb-1">{label}</p>
      <div className="font-medium text-sm">{children}</div>
    </div>
  )
}

function observedExpectedAction(log: AuditLog): ExpectedTestAction | undefined {
  if (log.action === "ALLOWED") return "allow"
  if (log.action === "REDACTED") return "redact"
  if (log.action === "BLOCKED") return "block"
  return undefined
}

function AuditDetailDrawer({ log, onClose, onCreateTest, onFeedbackSaved }: AuditDetailDrawerProps) {
  const [feedback, setFeedback] = useState<DecisionFeedback | null>(null)
  const [decision, setDecision] = useState<ReviewDecision>("unsure")
  const [expectedAction, setExpectedAction] = useState<ExpectedTestAction | "">("")
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus>("open")
  const [note, setNote] = useState("")
  const [isLoadingFeedback, setIsLoadingFeedback] = useState(false)
  const [isSavingFeedback, setIsSavingFeedback] = useState(false)
  const [feedbackLoadError, setFeedbackLoadError] = useState<string | null>(null)
  const [feedbackSaveError, setFeedbackSaveError] = useState<string | null>(null)
  const [feedbackRetry, setFeedbackRetry] = useState(0)
  const feedbackOwner = useRef(0)
  const savingFeedback = useRef(false)
  const { dialogRef, handleCancel, handleKeyDown, handleBackdropClick } = useNativeModalDialog({
    isOpen: Boolean(log),
    onClose,
  })
  const logId = log?.id

  useEffect(() => {
    const owner = ++feedbackOwner.current
    if (!logId) {
      setFeedback(null)
      setIsLoadingFeedback(false)
      setFeedbackLoadError(null)
      return
    }
    const controller = new AbortController()
    setFeedback(null)
    setDecision("unsure")
    setExpectedAction("")
    setReviewStatus("open")
    setNote("")
    setFeedbackLoadError(null)
    setFeedbackSaveError(null)
    savingFeedback.current = false
    setIsSavingFeedback(false)
    setIsLoadingFeedback(true)
    void fetchDecisionFeedback(logId, controller.signal)
      .then((current) => {
        if (owner !== feedbackOwner.current || controller.signal.aborted) return
        setFeedback(current)
        if (current) {
          setDecision(current.decision)
          setExpectedAction(current.expected_action ?? "")
          setReviewStatus(current.status)
          setNote(current.note ?? "")
        }
      })
      .catch((error: unknown) => {
        if (owner === feedbackOwner.current && !controller.signal.aborted) {
          setFeedbackLoadError(getErrorMessage(error, "Could not load the decision review."))
        }
      })
      .finally(() => {
        if (owner === feedbackOwner.current && !controller.signal.aborted) setIsLoadingFeedback(false)
      })
    return () => {
      controller.abort()
      feedbackOwner.current += 1
    }
  }, [logId, feedbackRetry])

  async function saveReview() {
    if (!log || savingFeedback.current) return
    savingFeedback.current = true
    setIsSavingFeedback(true)
    setFeedbackSaveError(null)
    const owner = feedbackOwner.current
    try {
      const saved = await saveDecisionFeedback(log.id, {
        decision,
        expected_action: decision === "incorrect" ? expectedAction || undefined : undefined,
        status: reviewStatus,
        note,
      })
      if (owner !== feedbackOwner.current) return
      setFeedback(saved)
      setDecision(saved.decision)
      setExpectedAction(saved.expected_action ?? "")
      setReviewStatus(saved.status)
      setNote(saved.note ?? "")
      onFeedbackSaved?.()
    } catch (error) {
      if (owner === feedbackOwner.current) setFeedbackSaveError(getErrorMessage(error, "Could not save the decision review."))
    } finally {
      if (owner === feedbackOwner.current) {
        savingFeedback.current = false
        setIsSavingFeedback(false)
      }
    }
  }

  if (!log) return null

  return (
    <dialog
      ref={dialogRef}
      id={`audit-drawer-${log.id}`}
      data-testid={`audit-drawer-${log.id}`}
      aria-labelledby="audit-detail-title"
      aria-modal="true"
      onCancel={handleCancel}
      onKeyDown={handleKeyDown}
      onClick={handleBackdropClick}
      className="fixed inset-0 m-0 h-full max-h-none w-full max-w-none border-0 bg-transparent p-0 text-white backdrop:bg-black/40"
    >
      <aside
        className="fixed top-0 right-0 h-full w-full max-w-xl bg-sidebar-bg border-l border-border-color shadow-2xl z-40 p-6 overflow-y-auto"
      >
      <div className="flex items-start justify-between mb-6">
        <div>
          <h3 id="audit-detail-title" className="text-xl font-bold">Audit Detail</h3>
          <p className="text-xs text-text-muted mt-1 break-all">{log.id}</p>
        </div>
        <button
          type="button"
          data-dialog-initial-focus
          onClick={onClose}
          className="text-text-muted hover:text-white transition-colors"
          aria-label="Close drawer"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="space-y-5 text-sm">
        <Field label="Timestamp">{formatTimestamp(log.created_at)}</Field>
        <Field label="Action">
          <span className={`uppercase ${log.action === "ERROR" ? "font-bold text-brand-red" : ""}`}>
            {actionLabel(log.action)}
          </span>
        </Field>
        <Field label="Reason">{inferReason(log)}</Field>
        <Field label="Hook Type">{log.hook_type}</Field>
        <Field label="Severity">{log.severity}</Field>
        {log.processing_ms !== null ? (
          <Field label="Processing Time">{log.processing_ms}ms</Field>
        ) : null}
        {log.policy_version !== null ? (
          <Field label="Policy Version">{log.policy_version}</Field>
        ) : null}
        {log.session_id ? <Field label="Session ID">{log.session_id}</Field> : null}
        {log.ip_address ? <Field label="IP Address">{log.ip_address}</Field> : null}
        <Field label="Algorand anchoring">
          {getAnchoringStatus(log) === "anchored" && log.algorand_tx_id ? (
            <a
              href={`https://testnet.explorer.perawallet.app/tx/${log.algorand_tx_id}`}
              target="_blank"
              rel="noreferrer"
              className="text-brand-green hover:underline font-mono text-xs"
            >
              {log.algorand_tx_id}
            </a>
          ) : (
            anchoringLabel(getAnchoringStatus(log))
          )}
        </Field>
        <Field label="Hash provenance">{hashProvenanceLabel(log)}</Field>
        {log.payload_hash ? (
          <Field label="Payload hash">
            <code className="block break-all text-xs">{log.payload_hash}</code>
          </Field>
        ) : null}
        {log.redacted_fields?.length ? (
          <Field label="Display sanitization">
            <span>
              Stored history is unchanged. Displayed values were sanitized in: {log.redacted_fields.join(", ")}.
              The hash remains stored as-is and has not been independently verified.
            </span>
          </Field>
        ) : null}

        <section className="rounded-xl border border-border-color bg-card-bg p-4" aria-labelledby="decision-review-title">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h4 id="decision-review-title" className="font-semibold">Decision review</h4>
              <p className="mt-1 text-xs text-text-muted">A human note for this audit record. It does not change the original event or protection rules.</p>
            </div>
            {feedback ? <span className="rounded-full border border-border-color px-2.5 py-1 text-[11px] text-text-muted">{feedback.status}</span> : null}
          </div>
          {feedbackLoadError ? <div role="alert" className="mt-3 rounded-lg border border-brand-red/30 bg-brand-red/10 p-2.5 text-xs text-red-200">{feedbackLoadError} <button type="button" className="ml-2 underline" disabled={isLoadingFeedback} onClick={() => setFeedbackRetry((current) => current + 1)}>Try again</button></div> : null}
          {feedbackSaveError ? <p role="alert" className="mt-3 rounded-lg border border-brand-red/30 bg-brand-red/10 p-2.5 text-xs text-red-200">{feedbackSaveError}</p> : null}
          {isLoadingFeedback ? <p role="status" className="mt-3 text-xs text-text-muted">Loading saved review…</p> : (
            <div className="mt-4 space-y-3">
              <div>
                <label htmlFor="decision-choice" className="mb-1.5 block text-xs text-text-muted">Was the decision correct?</label>
                <select id="decision-choice" value={decision} disabled={isLoadingFeedback || isSavingFeedback || Boolean(feedbackLoadError)} onChange={(event) => setDecision(event.target.value as ReviewDecision)} className="w-full rounded-lg border border-border-color bg-dashboard-bg px-3 py-2 text-sm disabled:opacity-50">
                  <option value="correct">Correct</option><option value="incorrect">Incorrect</option><option value="unsure">Unsure</option>
                </select>
              </div>
              {decision === "incorrect" ? (
                <div>
                  <label htmlFor="expected-review-action" className="mb-1.5 block text-xs text-text-muted">Expected outcome</label>
                  <select id="expected-review-action" required value={expectedAction} disabled={isLoadingFeedback || isSavingFeedback || Boolean(feedbackLoadError)} onChange={(event) => setExpectedAction(event.target.value as ExpectedTestAction | "")} className="w-full rounded-lg border border-border-color bg-dashboard-bg px-3 py-2 text-sm disabled:opacity-50">
                    <option value="">Choose outcome</option><option value="allow">Allow</option><option value="redact">Redact</option><option value="block">Block</option>
                  </select>
                </div>
              ) : null}
              <div>
                <label htmlFor="review-status" className="mb-1.5 block text-xs text-text-muted">Review status</label>
                <select id="review-status" value={reviewStatus} disabled={isLoadingFeedback || isSavingFeedback || Boolean(feedbackLoadError)} onChange={(event) => setReviewStatus(event.target.value as ReviewStatus)} className="w-full rounded-lg border border-border-color bg-dashboard-bg px-3 py-2 text-sm disabled:opacity-50"><option value="open">Open</option><option value="resolved">Resolved</option></select>
              </div>
              <div>
                <label htmlFor="review-note" className="mb-1.5 block text-xs text-text-muted">Note (optional, up to 500 characters)</label>
                <textarea id="review-note" maxLength={500} rows={3} value={note} disabled={isLoadingFeedback || isSavingFeedback || Boolean(feedbackLoadError)} onChange={(event) => setNote(event.target.value)} className="w-full resize-y rounded-lg border border-border-color bg-dashboard-bg px-3 py-2 text-sm disabled:opacity-50" />
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => void saveReview()} disabled={isLoadingFeedback || isSavingFeedback || Boolean(feedbackLoadError) || (decision === "incorrect" && !expectedAction)} className="rounded-lg bg-brand-green px-3.5 py-2 text-xs font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50">{isSavingFeedback ? "Saving…" : feedback ? "Save review" : "Save decision"}</button>
                {feedback && onCreateTest ? (
                  <button type="button" disabled={isLoadingFeedback || Boolean(feedbackLoadError) || isSavingFeedback} onClick={() => onCreateTest({ sourceFeedbackId: feedback.id, expectedAction: feedback.expected_action ?? observedExpectedAction(log), name: `Follow-up for ${log.action.toLowerCase()} event` })} className="rounded-lg border border-border-color px-3.5 py-2 text-xs hover:border-brand-green disabled:cursor-not-allowed disabled:opacity-50">Create synthetic follow-up</button>
                ) : null}
              </div>
            </div>
          )}
        </section>

        <div>
          <p className="text-text-muted mb-1">Sanitized Input Preview</p>
          <pre className="bg-card-bg border border-border-color rounded-lg p-3 overflow-auto text-xs whitespace-pre-wrap break-all">
            {JSON.stringify({ input_preview: log.input_preview }, null, 2)}
          </pre>
        </div>

        <div>
          <p className="text-text-muted mb-1">Guardrail Decision Details</p>
          <pre className="bg-card-bg border border-border-color rounded-lg p-3 overflow-auto text-xs whitespace-pre-wrap break-all">
            {JSON.stringify(log.details, null, 2)}
          </pre>
        </div>
      </div>
    </aside>
    </dialog>
  )
}

export default AuditDetailDrawer
