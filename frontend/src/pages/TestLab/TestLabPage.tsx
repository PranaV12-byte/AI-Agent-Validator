import { useEffect, useRef, useState, type FormEvent, type RefObject } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { Check, FlaskConical, Pencil, Play, Plus, RotateCw, Trash2 } from "lucide-react"

import { useNativeModalDialog } from "../../hooks/useNativeModalDialog"
import { getErrorMessage } from "../../services/apiClient"
import {
  createTestCase,
  deleteTestCase,
  fetchTestCases,
  runTestCases,
  updateTestCase,
} from "../../services/testLabService"
import type { ExpectedTestAction, TestCase, TestCasePayload, TestResult, TestRunStatus } from "../../types/api"

const CASE_LIMIT = 20
const MAX_PROMPT_LENGTH = 4000
type EditorDraft = {
  id?: string
  revision?: number
  name: string
  prompt: string
  expectedAction: ExpectedTestAction | ""
  acknowledged: boolean
  sourceFeedbackId?: string
}
type TestLabLocationState = {
  draft?: Omit<EditorDraft, "acknowledged" | "prompt" | "expectedAction"> & {
    prompt?: string
    expectedAction?: ExpectedTestAction
  }
} | null

function statusCopy(status: TestRunStatus): { label: string; style: string } {
  switch (status) {
    case "passed": return { label: "Matching expected outcome", style: "text-brand-green border-brand-green/30 bg-brand-green/10" }
    case "mismatch": return { label: "Outcome differs", style: "text-amber-300 border-amber-300/30 bg-amber-300/10" }
    case "unavailable": return { label: "Unavailable", style: "text-brand-red border-brand-red/30 bg-brand-red/10" }
    case "not_run": return { label: "Not run", style: "text-text-muted border-border-color bg-white/5" }
    case "stale": return { label: "Stale result", style: "text-amber-300 border-amber-300/30 bg-amber-300/10" }
    case "revision_conflict": return { label: "Case changed during run", style: "text-amber-300 border-amber-300/30 bg-amber-300/10" }
  }
}

function actionLabel(action: ExpectedTestAction | null): string {
  if (!action) return "No observed outcome"
  return action[0].toUpperCase() + action.slice(1)
}

function unavailableCopy(result: TestResult): string {
  if (result.failure_codes.includes("external_judge_required")) {
    return "This policy needs an external judge. Test Lab does not call providers, so no result was produced."
  }
  if (result.failure_codes.includes("snapshot_unavailable")) {
    return "A complete, current settings snapshot was unavailable. No outcome was scored."
  }
  if (result.failure_codes.includes("settings_unavailable")) {
    return "Current guardrail settings could not be loaded. No outcome was scored."
  }
  if (result.failure_codes.includes("case_revision_changed")) {
    return "This case was edited while it was running. Run the updated case again."
  }
  if (result.failure_codes.includes("run_deadline_exceeded")) {
    return "The local evaluation did not finish before the time limit. No outcome was scored."
  }
  return "The local evaluation could not produce a complete result. No outcome was scored."
}

function CaseEditor({
  draft,
  isSaving,
  error,
  fallbackFocusRef,
  onClose,
  onSave,
}: {
  draft: EditorDraft | null
  isSaving: boolean
  error: string | null
  fallbackFocusRef: RefObject<HTMLElement | null>
  onClose: () => void
  onSave: (payload: TestCasePayload, sourceFeedbackId?: string) => void
}) {
  const [name, setName] = useState(draft?.name ?? "")
  const [prompt, setPrompt] = useState(draft?.prompt ?? "")
  const [expectedAction, setExpectedAction] = useState<ExpectedTestAction | "">(draft?.expectedAction ?? "")
  const [acknowledged, setAcknowledged] = useState(draft?.acknowledged ?? false)
  const { dialogRef, handleCancel, handleKeyDown, handleBackdropClick } = useNativeModalDialog({
    isOpen: Boolean(draft),
    onClose,
    fallbackFocusRef,
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!draft || !acknowledged || !expectedAction || isSaving) return
    onSave({
      name,
      prompt,
      expected_action: expectedAction,
      synthetic_data_acknowledged: true,
      ...(draft.revision ? { revision: draft.revision } : {}),
    }, draft.sourceFeedbackId)
  }

  if (!draft) return null
  const isEditing = Boolean(draft.id)
  return (
    <dialog
      ref={dialogRef}
      data-testid="test-case-editor"
      aria-labelledby="test-case-editor-title"
      aria-modal="true"
      onCancel={handleCancel}
      onKeyDown={handleKeyDown}
      onClick={handleBackdropClick}
      className="fixed inset-0 m-0 h-full max-h-none w-full max-w-none border-0 bg-transparent p-0 text-white backdrop:bg-black/50"
    >
      <div className="mx-auto mt-[5vh] w-[min(94vw,42rem)] max-h-[90vh] overflow-y-auto rounded-2xl border border-border-color bg-sidebar-bg p-5 shadow-2xl sm:p-7">
        <form onSubmit={submit} className="space-y-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 id="test-case-editor-title" className="text-xl font-bold">{isEditing ? "Edit synthetic test" : "New synthetic test"}</h2>
              <p className="mt-1 text-sm text-text-muted">{draft.sourceFeedbackId ? "Write a synthetic equivalent from scratch. Activity History stores short excerpts, not complete messages." : "Save a reusable scenario and expected outcome."}</p>
            </div>
            <button type="button" onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-text-muted hover:bg-white/5 hover:text-white">Close</button>
          </div>
          {error ? <p role="alert" className="rounded-lg border border-brand-red/30 bg-brand-red/10 p-3 text-sm text-red-200">{error}</p> : null}
          <div>
            <label htmlFor="test-case-name" className="mb-2 block text-sm text-text-muted">Test name</label>
            <input id="test-case-name" data-dialog-initial-focus maxLength={120} required value={name} disabled={isSaving} onChange={(event) => setName(event.target.value)} className="w-full rounded-lg border border-border-color bg-dashboard-bg px-3 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-brand-green disabled:opacity-50" />
          </div>
          <div>
            <div className="mb-2 flex items-center justify-between gap-3">
              <label htmlFor="test-case-prompt" className="block text-sm text-text-muted">Synthetic test prompt</label>
              <span className="text-xs text-text-muted">{prompt.length}/{MAX_PROMPT_LENGTH}</span>
            </div>
            <textarea id="test-case-prompt" required maxLength={MAX_PROMPT_LENGTH} rows={6} value={prompt} disabled={isSaving} onChange={(event) => setPrompt(event.target.value)} placeholder="Example: A fictional customer asks to update a made-up account number…" className="w-full resize-y rounded-lg border border-border-color bg-dashboard-bg px-3 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-brand-green disabled:opacity-50" />
            <p className="mt-1 text-xs text-text-muted">Use made-up details. Don’t paste passwords or API keys.</p>
          </div>
          <div>
            <label htmlFor="expected-action" className="mb-2 block text-sm text-text-muted">Expected guardrail outcome</label>
            <select id="expected-action" required value={expectedAction} disabled={isSaving} onChange={(event) => setExpectedAction(event.target.value as ExpectedTestAction | "")} className="w-full rounded-lg border border-border-color bg-dashboard-bg px-3 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-brand-green disabled:opacity-50">
              <option value="">Choose expected outcome</option>
              <option value="allow">Allow</option><option value="redact">Redact</option><option value="block">Block</option>
            </select>
          </div>
          <label className="flex items-start gap-3 rounded-lg border border-border-color bg-dashboard-bg p-3 text-sm">
            <input type="checkbox" checked={acknowledged} disabled={isSaving} onChange={(event) => setAcknowledged(event.target.checked)} className="mt-0.5 accent-brand-green disabled:opacity-50" />
            <span>I confirm this prompt contains synthetic data and no real personal information or credentials.</span>
          </label>
          <div className="flex flex-col-reverse gap-2 border-t border-border-color pt-4 sm:flex-row sm:justify-end">
            <button type="button" onClick={onClose} className="rounded-lg border border-border-color px-4 py-2.5 text-sm hover:bg-white/5">Cancel</button>
            <button type="submit" disabled={isSaving || !acknowledged || !expectedAction || !name.trim() || !prompt.trim()} className="rounded-lg bg-brand-green px-4 py-2.5 text-sm font-semibold text-black hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">{isSaving ? "Saving…" : isEditing ? "Save changes" : "Save test"}</button>
          </div>
        </form>
      </div>
    </dialog>
  )
}

function DeleteCaseDialog({
  testCase,
  isDeleting,
  onCancel,
  onConfirm,
}: {
  testCase: TestCase | null
  isDeleting: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const { dialogRef, handleCancel, handleKeyDown } = useNativeModalDialog({ isOpen: Boolean(testCase), onClose: onCancel })
  if (!testCase) return null
  return (
    <dialog ref={dialogRef} data-testid="delete-test-case-dialog" aria-labelledby="delete-test-case-title" aria-modal="true" onCancel={handleCancel} onKeyDown={handleKeyDown} className="fixed inset-0 m-0 h-full max-h-none w-full max-w-none border-0 bg-transparent p-0 text-white backdrop:bg-black/50">
      <div className="mx-auto mt-[20vh] w-[min(92vw,28rem)] rounded-2xl border border-border-color bg-sidebar-bg p-6 shadow-2xl">
        <h2 id="delete-test-case-title" className="text-xl font-bold">Delete test case?</h2>
        <p className="mt-2 text-sm text-text-muted">“{testCase.name}” and its saved result will be permanently deleted.</p>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onCancel} disabled={isDeleting} className="rounded-lg border border-border-color px-4 py-2 text-sm">Cancel</button>
          <button type="button" data-dialog-initial-focus onClick={onConfirm} disabled={isDeleting} className="rounded-lg bg-brand-red px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{isDeleting ? "Deleting…" : "Delete"}</button>
        </div>
      </div>
    </dialog>
  )
}

function ResultCard({ result }: { result: TestResult }) {
  const copy = statusCopy(result.status)
  return (
    <div className="mt-4 border-t border-border-color pt-4 text-sm">
      <div className={`inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${copy.style}`}>
        {result.status === "passed" ? <Check className="h-3.5 w-3.5" /> : null}{copy.label}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 text-xs sm:text-sm">
        <p><span className="text-text-muted">Expected:</span> {actionLabel(result.expected_action)}</p>
        <p><span className="text-text-muted">Observed:</span> {actionLabel(result.observed_action)}</p>
      </div>
      {result.status === "unavailable" || result.status === "not_run" || result.status === "revision_conflict" ? <p className="mt-3 text-xs leading-relaxed text-text-muted">{unavailableCopy(result)}</p> : null}
      {result.preview ? <p className="mt-3 break-words rounded-lg bg-dashboard-bg p-3 text-xs text-text-muted">Sanitized output preview: {result.preview}</p> : null}
      {result.status === "passed" ? <p className="mt-3 text-xs leading-relaxed text-text-muted">A match means only that the observed action matched this expected outcome. It does not prove complete redaction or overall security accuracy.</p> : null}
      {Object.keys(result.redaction_counts).length ? <p className="mt-2 text-xs text-text-muted">Redactions reported: {Object.entries(result.redaction_counts).map(([kind, count]) => `${kind} ${count}`).join(" · ")}</p> : null}
      <p className="mt-2 text-[11px] text-text-muted">Checked {new Date(result.completed_at).toLocaleString()}</p>
    </div>
  )
}

function TestLabPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const initialLocationState = location.state as TestLabLocationState
  const [cases, setCases] = useState<TestCase[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [editor, setEditor] = useState<EditorDraft | null>(() => initialLocationState?.draft ? {
    ...initialLocationState.draft,
    prompt: "",
    expectedAction: initialLocationState.draft.expectedAction ?? "",
    acknowledged: false,
  } : null)
  const [isSaving, setIsSaving] = useState(false)
  const [editorError, setEditorError] = useState<string | null>(null)
  const [caseToDelete, setCaseToDelete] = useState<TestCase | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [runningIds, setRunningIds] = useState<string[]>([])
  const [isRunningAll, setIsRunningAll] = useState(false)
  const addButtonRef = useRef<HTMLButtonElement>(null)
  const pageOwnerRef = useRef(0)
  const loadOwnerRef = useRef(0)
  const editorOwnerRef = useRef(0)
  const savingRef = useRef(false)
  const deletingRef = useRef(false)

  async function loadCases(signal?: AbortSignal): Promise<TestCase[] | null> {
    const owner = ++loadOwnerRef.current
    setIsLoading(true)
    setLoadError(null)
    try {
      const result = await fetchTestCases(signal)
      if (!signal?.aborted && owner === loadOwnerRef.current) {
        setCases(result)
        return result
      }
    } catch {
      if (!signal?.aborted && owner === loadOwnerRef.current) setLoadError("Could not load saved test cases.")
    } finally {
      if (!signal?.aborted && owner === loadOwnerRef.current) setIsLoading(false)
    }
    return null
  }

  useEffect(() => {
    const controller = new AbortController()
    void loadCases(controller.signal)
    return () => {
      controller.abort()
      pageOwnerRef.current += 1
      loadOwnerRef.current += 1
    }
  }, [])

  useEffect(() => {
    if (initialLocationState?.draft) navigate(location.pathname, { replace: true, state: null })
  }, [initialLocationState, location.pathname, navigate])

  function openEditor(draft: EditorDraft) {
    setEditorError(null)
    editorOwnerRef.current += 1
    setEditor(draft)
  }

  function closeEditor() {
    editorOwnerRef.current += 1
    setIsSaving(false)
    savingRef.current = false
    setEditorError(null)
    setEditor(null)
  }

  async function saveCase(payload: TestCasePayload, sourceFeedbackId?: string) {
    if (!editor || savingRef.current) return
    savingRef.current = true
    setIsSaving(true)
    setEditorError(null)
    const owner = editorOwnerRef.current
    try {
      if (editor.id && editor.revision) {
        await updateTestCase(editor.id, { ...payload, revision: editor.revision })
      } else {
        await createTestCase(payload, sourceFeedbackId)
      }
      if (owner !== editorOwnerRef.current) return
      closeEditor()
      toast.success(editor.id ? "Test case updated" : "Synthetic test saved")
      await loadCases()
    } catch (error) {
      if (owner === editorOwnerRef.current) setEditorError(getErrorMessage(error, "Could not save this test case."))
    } finally {
      if (owner === editorOwnerRef.current) {
        savingRef.current = false
        setIsSaving(false)
      }
    }
  }

  async function deleteCase() {
    if (!caseToDelete || deletingRef.current) return
    deletingRef.current = true
    setIsDeleting(true)
    const owner = pageOwnerRef.current
    try {
      await deleteTestCase(caseToDelete.id)
      if (owner !== pageOwnerRef.current) return
      setCaseToDelete(null)
      await loadCases()
      toast.success("Test case deleted")
    } catch (error) {
      if (owner === pageOwnerRef.current) toast.error(getErrorMessage(error, "Could not delete this test case."))
    } finally {
      if (owner === pageOwnerRef.current) {
        deletingRef.current = false
        setIsDeleting(false)
      }
    }
  }

  async function runCases(ids?: string[]) {
    if (isRunningAll || runningIds.length > 0) return
    setRunError(null)
    if (ids) setRunningIds(ids)
    else setIsRunningAll(true)
    const owner = pageOwnerRef.current
    try {
      const response = await runTestCases(ids)
      if (owner !== pageOwnerRef.current) return
      const currentCases = await loadCases()
      if (owner !== pageOwnerRef.current) return
      if (!currentCases) {
        toast.message("Run completed. Refresh to confirm the latest results.")
        return
      }
      const runIds = new Set(response.results.map((result) => result.case_id))
      const reconciledCases = currentCases.map((testCase) => {
        const attempt = response.results.find((result) => result.case_id === testCase.id)
        if (!attempt) return testCase

        const persistenceFailed = attempt.failure_codes.some((code) =>
          code === "result_persistence_failed" || code === "result_commit_failed",
        )
        const attemptConflict = attempt.status === "revision_conflict"
        if ((!persistenceFailed && !attemptConflict) || (!attemptConflict && attempt.case_revision !== testCase.revision)) return testCase

        const persistedAt = testCase.last_result?.completed_at
        const attemptAt = Date.parse(attempt.completed_at)
        if (persistedAt && Date.parse(persistedAt) >= attemptAt) return testCase
        return { ...testCase, last_result: attempt, last_run_at: attempt.completed_at }
      })
      setCases(reconciledCases)
      const matching = reconciledCases.filter((testCase) => runIds.has(testCase.id) && testCase.last_result?.status === "passed").length
      toast.success(`${matching} matching outcome${matching === 1 ? "" : "s"}`)
    } catch (error) {
      if (owner === pageOwnerRef.current) setRunError(getErrorMessage(error, "The test run could not be completed. Saved cases were not changed."))
    } finally {
      if (owner === pageOwnerRef.current) {
        setRunningIds([])
        setIsRunningAll(false)
      }
    }
  }

  const isBusy = isRunningAll || runningIds.length > 0
  const canCreate = cases.length < CASE_LIMIT

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex gap-3">
          <div className="mt-1 rounded-xl border border-brand-green/30 bg-brand-green/10 p-3 text-brand-green"><FlaskConical className="h-6 w-6" /></div>
          <div>
            <h1 className="text-3xl font-bold">Test Lab</h1>
            <p className="mt-1 max-w-2xl text-sm text-text-muted">Check your current rules against saved examples using made-up scenarios. Runs compare only the observed action with your expected outcome.</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
          <button type="button" onClick={() => void runCases()} disabled={isLoading || cases.length === 0 || isBusy} className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm disabled:cursor-not-allowed disabled:opacity-50 ${cases.length > 0 ? "bg-brand-green font-semibold text-black hover:brightness-110" : "border border-border-color hover:border-brand-green"}`}><Play className="h-4 w-4" />{isRunningAll ? "Running…" : "Run all"}</button>
          <button ref={addButtonRef} type="button" onClick={() => openEditor({ name: "", prompt: "", expectedAction: "allow", acknowledged: false })} disabled={!canCreate} className="inline-flex items-center justify-center gap-2 rounded-lg border border-border-color px-4 py-2.5 text-sm hover:border-brand-green disabled:cursor-not-allowed disabled:opacity-50"><Plus className="h-4 w-4" />New test</button>
        </div>
      </header>

      <div className="flex flex-col gap-2 rounded-xl border border-border-color bg-card-bg p-4 text-sm text-text-muted sm:flex-row sm:items-start">
        <div className="shrink-0 font-semibold text-white">Synthetic tests</div>
        <p>Use fictional data only. A matching outcome does not establish complete redaction or overall security accuracy. Policies that need an external judge are unavailable; Test Lab does not contact providers.</p>
      </div>

      <div className="flex items-center justify-between text-xs text-text-muted">
        <span>{cases.length} of {CASE_LIMIT} saved cases</span>
        <button type="button" onClick={() => void loadCases()} disabled={isLoading} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 hover:text-white disabled:opacity-50"><RotateCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />Refresh</button>
      </div>

      {runError ? <div role="alert" className="rounded-lg border border-brand-red/30 bg-brand-red/10 p-3 text-sm text-red-200">{runError}</div> : null}
      {loadError ? <div role="alert" className="rounded-lg border border-brand-red/30 bg-brand-red/10 p-4 text-sm text-red-200">{loadError} <button type="button" className="ml-2 underline" onClick={() => void loadCases()}>Try again</button></div> : null}

      {isLoading && cases.length === 0 ? <div className="rounded-2xl border border-border-color bg-card-bg p-10 text-center text-sm text-text-muted">Loading saved tests…</div> : null}
      {!isLoading && !loadError && cases.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border-color bg-card-bg p-8 text-center sm:p-12">
          <FlaskConical className="mx-auto h-8 w-8 text-brand-green" />
          <h2 className="mt-4 text-lg font-semibold">Start with one synthetic scenario</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-text-muted">Write a made-up prompt, choose the action you expect, then run it against the current settings.</p>
          <button type="button" onClick={() => openEditor({ name: "", prompt: "", expectedAction: "allow", acknowledged: false })} className="mt-5 rounded-lg bg-brand-green px-4 py-2.5 text-sm font-semibold text-black">Create a test</button>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {cases.map((testCase) => {
          const result = testCase.last_result
          const isRunning = isRunningAll || runningIds.includes(testCase.id)
          const isStale = result?.status === "stale"
          return (
            <article key={testCase.id} className="rounded-2xl border border-border-color bg-card-bg p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="break-words text-base font-semibold">{testCase.name}</h2>
                  <p className="mt-1 text-xs text-text-muted">Expected: {actionLabel(testCase.expected_action)} · Revision {testCase.revision}</p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button type="button" aria-label={`Run ${testCase.name}`} onClick={() => void runCases([testCase.id])} disabled={isBusy} className="rounded-lg p-2 text-text-muted hover:bg-white/5 hover:text-brand-green disabled:opacity-40"><Play className="h-4 w-4" /></button>
                  <button type="button" aria-label={`Edit ${testCase.name}`} onClick={() => openEditor({ id: testCase.id, revision: testCase.revision, name: testCase.name, prompt: testCase.prompt, expectedAction: testCase.expected_action, acknowledged: testCase.synthetic_data_acknowledged })} disabled={isBusy} className="rounded-lg p-2 text-text-muted hover:bg-white/5 hover:text-white disabled:opacity-40"><Pencil className="h-4 w-4" /></button>
                  <button type="button" aria-label={`Delete ${testCase.name}`} onClick={() => setCaseToDelete(testCase)} disabled={isBusy} className="rounded-lg p-2 text-text-muted hover:bg-white/5 hover:text-brand-red disabled:opacity-40"><Trash2 className="h-4 w-4" /></button>
                </div>
              </div>
              <details className="mt-4">
                <summary className="cursor-pointer text-xs text-text-muted">View synthetic prompt</summary>
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-dashboard-bg p-3 text-xs text-text-muted">{testCase.prompt}</pre>
              </details>
              {isRunning ? <p role="status" className="mt-4 border-t border-border-color pt-4 text-sm text-text-muted">Evaluating against a frozen settings snapshot…</p> : null}
              {!isRunning && result ? <ResultCard result={result} /> : null}
              {!isRunning && !result ? <p className="mt-4 border-t border-border-color pt-4 text-xs text-text-muted">Not run yet</p> : null}
              {isStale ? <p className="mt-2 text-xs text-amber-300">Settings, rules, or this case changed since the last result. Run again to refresh it.</p> : null}
            </article>
          )
        })}
      </div>

      {!canCreate ? <p className="text-xs text-text-muted">The 20-case limit is reached. Delete a case to create another.</p> : null}
      {isBusy ? <div className="sr-only" role="status">{isRunningAll ? "Running all tests" : `Running ${runningIds.length} test${runningIds.length === 1 ? "" : "s"}`}</div> : null}

      {editor ? <CaseEditor key={editor.id ?? editor.sourceFeedbackId ?? "new"} draft={editor} isSaving={isSaving} error={editorError} fallbackFocusRef={addButtonRef} onClose={closeEditor} onSave={(payload, sourceFeedbackId) => void saveCase(payload, sourceFeedbackId)} /> : null}
      <DeleteCaseDialog testCase={caseToDelete} isDeleting={isDeleting} onCancel={() => setCaseToDelete(null)} onConfirm={() => void deleteCase()} />
    </div>
  )
}

export default TestLabPage
