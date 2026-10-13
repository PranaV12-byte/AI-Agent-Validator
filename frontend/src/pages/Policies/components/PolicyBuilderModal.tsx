import { X } from "lucide-react"
import { useEffect, useMemo, useRef, useState, type RefObject } from "react"

import { useNativeModalDialog } from "../../../hooks/useNativeModalDialog"
import type { Policy, PolicyCreatePayload, PolicyRuleType } from "../../../types/api"

type PolicyBuilderModalProps = {
  mode: "create" | "edit"
  policy: Policy | null
  isOpen: boolean
  isSaving: boolean
  fallbackFocusRef?: RefObject<HTMLElement | null>
  onClose: () => void
  onSave: (payload: PolicyCreatePayload) => Promise<void>
}

const RULE_TYPE_OPTIONS: Array<{ label: string; value: PolicyRuleType; description: string }> = [
  {
    label: "Hide Personal Info",
    value: "pii_redaction",
    description: "Redact Aadhaar, PAN, email, Indian phone numbers, and UPI IDs from messages.",
  },
  {
    label: "Block Manipulation",
    value: "prompt_injection",
    description: "Stop attempts to trick or hijack your AI into doing something it shouldn't.",
  },
  {
    label: "Pattern Match",
    value: "regex_match",
    description: "Advanced: match messages using a text pattern (e.g. phone number formats).",
  },
  {
    label: "AI Content Check",
    value: "llm_eval",
    description: "Use AI to judge whether a message violates a rule you describe in plain English.",
  },
  {
    label: "Word Match",
    value: "keyword",
    description: "Block messages containing your selected word or phrase.",
  },
  {
    label: "Meaning Match",
    value: "semantic",
    description: "Experimental text-similarity match; review results before relying on it.",
  },
]

const PII_TYPE_OPTIONS = [
  { label: "Aadhaar", value: "aadhaar" },
  { label: "PAN", value: "pan" },
  { label: "Email", value: "email" },
  { label: "Phone", value: "phone" },
  { label: "UPI ID", value: "upi" },
]
const DEFAULT_PII_TYPES = PII_TYPE_OPTIONS.map((option) => option.value)
const INJECTION_SENSITIVITIES = ["strict", "moderate", "lenient"] as const
const REGEX_VALIDATION_MESSAGES = new Set([
  "regex_match pattern is invalid",
  "regex_match requires parameters.pattern as non-empty string",
  "regex_match pattern must be at most 256 characters",
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}

function isRegexValidationMessage(value: unknown): value is string {
  if (typeof value !== "string") return false
  const normalized = value.trim().toLowerCase().replace(/^value error,\s*/, "")
  return REGEX_VALIDATION_MESSAGES.has(normalized)
}

function isInvalidRegexResponse(error: unknown): boolean {
  if (!isRecord(error) || !isRecord(error.response) || error.response.status !== 422) {
    return false
  }

  const data = error.response.data
  if (!isRecord(data)) return false

  if (typeof data.detail === "string") {
    return isRegexValidationMessage(data.detail)
  }
  if (!Array.isArray(data.detail)) return false

  return data.detail.some((issue: unknown) => {
    if (!isRecord(issue) || !Array.isArray(issue.loc)) return false
    const requestLocation = issue.loc.some(
      (segment: unknown) => segment === "body" || segment === "parameters" || segment === "pattern",
    )
    return requestLocation && isRegexValidationMessage(issue.msg)
  })
}

function PolicyBuilderModal({
  mode,
  policy,
  isOpen,
  isSaving,
  fallbackFocusRef,
  onClose,
  onSave,
}: PolicyBuilderModalProps) {
  const [name, setName] = useState(policy?.name ?? "")
  const [description, setDescription] = useState(policy?.description ?? "")
  const [ruleType, setRuleType] = useState<PolicyRuleType>(policy?.rule_type ?? "semantic")
  const [ruleText, setRuleText] = useState(policy?.rule_text ?? "")
  const [regexPattern, setRegexPattern] = useState(
    String(policy?.parameters?.pattern ?? ""),
  )
  const [llmRubric, setLlmRubric] = useState(String(policy?.parameters?.rubric ?? ""))
  const [keyword, setKeyword] = useState(String(policy?.parameters?.keyword ?? ""))
  const [piiTypes, setPiiTypes] = useState<string[]>(() => {
    const configured = policy?.parameters?.pii_types
    return Array.isArray(configured)
      ? configured.filter((value): value is string => typeof value === "string")
      : DEFAULT_PII_TYPES
  })
  const [injectionSensitivity, setInjectionSensitivity] = useState(
    String(policy?.parameters?.sensitivity ?? "moderate"),
  )
  const [semanticThreshold, setSemanticThreshold] = useState(() => {
    const configured = policy?.parameters?.threshold
    return typeof configured === "number" && Number.isFinite(configured)
      ? String(configured)
      : ""
  })
  const [patternError, setPatternError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const formRevisionRef = useRef(0)

  function invalidatePendingSave() {
    formRevisionRef.current += 1
  }

  function handleClose() {
    invalidatePendingSave()
    onClose()
  }

  function handleFormEdit() {
    invalidatePendingSave()
    setSaveError(null)
  }

  const { dialogRef, handleCancel, handleKeyDown, handleBackdropClick } = useNativeModalDialog({
    isOpen,
    onClose: handleClose,
    fallbackFocusRef,
  })

  useEffect(() => {
    formRevisionRef.current += 1
    setName(policy?.name ?? "")
    setDescription(policy?.description ?? "")
    setRuleType(policy?.rule_type ?? "semantic")
    setRuleText(policy?.rule_text ?? "")
    setRegexPattern(String(policy?.parameters?.pattern ?? ""))
    setLlmRubric(String(policy?.parameters?.rubric ?? ""))
    setKeyword(String(policy?.parameters?.keyword ?? ""))
    const configuredPiiTypes = policy?.parameters?.pii_types
    setPiiTypes(
      Array.isArray(configuredPiiTypes)
        ? configuredPiiTypes.filter((value): value is string => typeof value === "string")
        : DEFAULT_PII_TYPES,
    )
    const configuredSensitivity = policy?.parameters?.sensitivity
    setInjectionSensitivity(
      typeof configuredSensitivity === "string" ? configuredSensitivity : "moderate",
    )
    const configuredThreshold = policy?.parameters?.threshold
    setSemanticThreshold(
      typeof configuredThreshold === "number" && Number.isFinite(configuredThreshold)
        ? String(configuredThreshold)
        : "",
    )
    setPatternError(null)
    setSaveError(null)
  }, [policy, isOpen])

  const isSaveDisabled = useMemo(() => {
    if (!name.trim() || !ruleText.trim()) {
      return true
    }
    if (ruleType === "regex_match" && !regexPattern.trim()) {
      return true
    }
    if (ruleType === "llm_eval" && !llmRubric.trim()) {
      return true
    }
    if (ruleType === "keyword" && !keyword.trim()) {
      return true
    }
    if (ruleType === "pii_redaction" && piiTypes.length === 0) {
      return true
    }
    if (
      ruleType === "prompt_injection" &&
      !INJECTION_SENSITIVITIES.includes(
        injectionSensitivity as (typeof INJECTION_SENSITIVITIES)[number],
      )
    ) {
      return true
    }
    if (ruleType === "semantic" && semanticThreshold.trim()) {
      const value = Number(semanticThreshold)
      if (!Number.isFinite(value) || value < 0 || value > 1) {
        return true
      }
    }
    return false
  }, [
    injectionSensitivity,
    keyword,
    llmRubric,
    name,
    piiTypes,
    regexPattern,
    ruleText,
    ruleType,
    semanticThreshold,
  ])

  async function handleSubmit() {
    const submittedRevision = formRevisionRef.current
    const parameters: Record<string, unknown> = {}
    if (ruleType === "regex_match") {
      parameters.pattern = regexPattern
    }
    if (ruleType === "llm_eval") {
      parameters.rubric = llmRubric
    }
    if (ruleType === "keyword") {
      parameters.keyword = keyword
    }
    if (ruleType === "pii_redaction") {
      parameters.pii_types = piiTypes
    }
    if (ruleType === "prompt_injection") {
      parameters.sensitivity = injectionSensitivity
    }
    if (ruleType === "semantic" && semanticThreshold.trim()) {
      parameters.threshold = Number(semanticThreshold)
    }

    setPatternError(null)
    setSaveError(null)
    try {
      await onSave({
        name: name.trim(),
        description: description.trim() || null,
        rule_text: ruleText.trim(),
        rule_type: ruleType,
        parameters,
      })
    } catch (error: unknown) {
      if (formRevisionRef.current !== submittedRevision) return

      if (ruleType === "regex_match" && isInvalidRegexResponse(error)) {
        setPatternError("Enter a valid Python regular-expression pattern.")
      } else {
        setSaveError("Could not save policy. Please review the form and try again.")
      }
    }
  }

  if (!isOpen) {
    return null
  }

  return (
    <dialog
      ref={dialogRef}
      data-testid="policy-builder-dialog"
      aria-labelledby="policy-builder-title"
      aria-modal="true"
      onCancel={handleCancel}
      onKeyDown={handleKeyDown}
      onClick={handleBackdropClick}
      onInput={handleFormEdit}
      onChange={handleFormEdit}
      className="fixed inset-0 m-0 h-full max-h-none w-full max-w-none border-0 bg-transparent p-0 text-white backdrop:bg-black/40"
    >
      <div className="fixed top-0 right-0 h-full w-full max-w-xl overflow-y-auto border-l border-border-color bg-sidebar-bg p-6 shadow-2xl">
      <div className="flex items-center justify-between mb-6">
        <h2 id="policy-builder-title" className="text-xl font-bold">{mode === "create" ? "New Protection Rule" : "Edit Protection Rule"}</h2>
        <button type="button" onClick={handleClose} className="text-text-muted hover:text-white" aria-label="Close panel">
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="space-y-5">
        <div>
          <label htmlFor="policy-name" className="block text-sm text-text-muted mb-2">
            Name
          </label>
          <input
            id="policy-name"
            data-dialog-initial-focus
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
          />
        </div>

        <div>
          <label htmlFor="policy-description" className="block text-sm text-text-muted mb-2">
            Description
          </label>
          <textarea
            id="policy-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
          />
        </div>

        <div>
          <label htmlFor="policy-rule-type" className="block text-sm text-text-muted mb-2">
            Protection type
          </label>
          <select
            id="policy-rule-type"
            data-testid="policy-rule-type"
            value={ruleType}
            onChange={(event) => {
              setRuleType(event.target.value as PolicyRuleType)
              setPatternError(null)
            }}
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
          >
            {RULE_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {RULE_TYPE_OPTIONS.find((o) => o.value === ruleType)?.description ? (
            <p className="text-xs text-text-muted mt-1">
              {RULE_TYPE_OPTIONS.find((o) => o.value === ruleType)?.description}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="policy-rule-text" className="block text-sm text-text-muted mb-2">
            What should this rule do? (describe in plain English)
          </label>
          <textarea
            id="policy-rule-text"
            value={ruleText}
            onChange={(event) => setRuleText(event.target.value)}
            rows={4}
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
          />
        </div>

        {ruleType === "regex_match" ? (
          <div>
            <label htmlFor="policy-regex-pattern" className="block text-sm text-text-muted mb-2">
              Text Pattern (e.g. \d{"{3}"}-\d{"{4}"} for phone numbers)
            </label>
            <input
              id="policy-regex-pattern"
              data-testid="policy-regex-pattern"
              aria-invalid={patternError ? true : undefined}
              aria-describedby={patternError ? "policy-regex-pattern-error" : undefined}
              value={regexPattern}
              onChange={(event) => {
                setRegexPattern(event.target.value)
                setPatternError(null)
              }}
              className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
            />
            {patternError ? (
              <p id="policy-regex-pattern-error" role="alert" className="mt-1 text-sm text-brand-red">
                {patternError}
              </p>
            ) : null}
          </div>
        ) : null}

        {ruleType === "llm_eval" ? (
          <div>
            <label htmlFor="policy-llm-rubric" className="block text-sm text-text-muted mb-2">
              Describe your rule in plain English
            </label>
            <textarea
              id="policy-llm-rubric"
              data-testid="policy-llm-rubric"
              value={llmRubric}
              onChange={(event) => setLlmRubric(event.target.value)}
              rows={4}
              className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
            />
          </div>
        ) : null}

        {ruleType === "keyword" ? (
          <div>
            <label htmlFor="policy-keyword" className="block text-sm text-text-muted mb-2">
              Word or phrase to block
            </label>
            <input
              id="policy-keyword"
              data-testid="policy-keyword"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
            />
          </div>
        ) : null}

        {ruleType === "pii_redaction" ? (
          <fieldset className="rounded-lg border border-border-color p-3">
            <legend className="px-1 text-sm text-text-muted">
              Personal information to redact
            </legend>
            <div className="grid grid-cols-2 gap-3">
              {PII_TYPE_OPTIONS.map((option) => (
                <label key={option.value} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    aria-label={`Redact ${option.label}`}
                    checked={piiTypes.includes(option.value)}
                    onChange={(event) => {
                      setPiiTypes((current) =>
                        event.target.checked
                          ? [...current, option.value]
                          : current.filter((value) => value !== option.value),
                      )
                    }}
                    className="accent-brand-green"
                  />
                  {option.label}
                </label>
              ))}
            </div>
            {piiTypes.length === 0 ? (
              <p className="mt-2 text-xs text-text-muted">Choose at least one category.</p>
            ) : null}
          </fieldset>
        ) : null}

        {ruleType === "prompt_injection" ? (
          <div>
            <label
              htmlFor="policy-injection-sensitivity"
              className="block text-sm text-text-muted mb-2"
            >
              Detection sensitivity
            </label>
            <select
              id="policy-injection-sensitivity"
              data-testid="policy-injection-sensitivity"
              value={injectionSensitivity}
              onChange={(event) => setInjectionSensitivity(event.target.value)}
              className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
            >
              {INJECTION_SENSITIVITIES.map((sensitivity) => (
                <option key={sensitivity} value={sensitivity}>
                  {sensitivity.charAt(0).toUpperCase() + sensitivity.slice(1)}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {ruleType === "semantic" ? (
          <div>
            <label
              htmlFor="policy-semantic-threshold"
              className="block text-sm text-text-muted mb-2"
            >
              Match threshold (optional, 0 to 1)
            </label>
            <input
              id="policy-semantic-threshold"
              data-testid="policy-semantic-threshold"
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={semanticThreshold}
              onChange={(event) => setSemanticThreshold(event.target.value)}
              className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
            />
          </div>
        ) : null}

        {saveError ? (
          <p role="alert" className="text-sm text-brand-red bg-brand-red/10 border border-brand-red/30 rounded-lg px-3 py-2">
            {saveError}
          </p>
        ) : null}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={handleClose}
            className="px-4 py-2 rounded-lg border border-border-color text-text-muted hover:text-white"
          >
            Cancel
          </button>
          <button
            type="button"
            data-testid="policy-save-button"
            disabled={isSaving || isSaveDisabled}
            onClick={() => void handleSubmit()}
            className="px-4 py-2 rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green hover:bg-brand-green/20 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
      </div>
    </dialog>
  )
}

export default PolicyBuilderModal
