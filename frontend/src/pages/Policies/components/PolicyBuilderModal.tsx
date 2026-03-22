import type { Policy, PolicyCreatePayload, PolicyRuleType } from "../../../types/api"
import { useEffect, useMemo, useState } from "react"

type PolicyBuilderModalProps = {
  mode: "create" | "edit"
  policy: Policy | null
  isOpen: boolean
  isSaving: boolean
  onClose: () => void
  onSave: (payload: PolicyCreatePayload) => Promise<void>
}

const RULE_TYPE_OPTIONS: Array<{ label: string; value: PolicyRuleType }> = [
  { label: "PII Redaction", value: "pii_redaction" },
  { label: "Prompt Injection", value: "prompt_injection" },
  { label: "Regex Match", value: "regex_match" },
  { label: "LLM Eval", value: "llm_eval" },
  { label: "Keyword", value: "keyword" },
  { label: "Semantic", value: "semantic" },
]

function PolicyBuilderModal({
  mode,
  policy,
  isOpen,
  isSaving,
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

  useEffect(() => {
    setName(policy?.name ?? "")
    setDescription(policy?.description ?? "")
    setRuleType(policy?.rule_type ?? "semantic")
    setRuleText(policy?.rule_text ?? "")
    setRegexPattern(String(policy?.parameters?.pattern ?? ""))
    setLlmRubric(String(policy?.parameters?.rubric ?? ""))
    setKeyword(String(policy?.parameters?.keyword ?? ""))
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
    return false
  }, [keyword, llmRubric, name, regexPattern, ruleText, ruleType])

  async function handleSubmit() {
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

    await onSave({
      name: name.trim(),
      description: description.trim() || null,
      rule_text: ruleText.trim(),
      rule_type: ruleType,
      parameters,
    })
  }

  if (!isOpen) {
    return null
  }

  return (
    <aside className="fixed top-0 right-0 h-full w-full max-w-xl bg-sidebar-bg border-l border-border-color shadow-2xl z-50 p-6 overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">{mode === "create" ? "New Policy" : "Edit Policy"}</h2>
        <button type="button" onClick={onClose} className="text-text-muted hover:text-white">
          Close
        </button>
      </div>

      <div className="space-y-5">
        <div>
          <label htmlFor="policy-name" className="block text-sm text-text-muted mb-2">
            Name
          </label>
          <input
            id="policy-name"
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
            Rule Type
          </label>
          <select
            id="policy-rule-type"
            data-testid="policy-rule-type"
            value={ruleType}
            onChange={(event) => setRuleType(event.target.value as PolicyRuleType)}
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
          >
            {RULE_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="policy-rule-text" className="block text-sm text-text-muted mb-2">
            Rule Text
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
              Regex Pattern
            </label>
            <input
              id="policy-regex-pattern"
              data-testid="policy-regex-pattern"
              value={regexPattern}
              onChange={(event) => setRegexPattern(event.target.value)}
              className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
            />
          </div>
        ) : null}

        {ruleType === "llm_eval" ? (
          <div>
            <label htmlFor="policy-llm-rubric" className="block text-sm text-text-muted mb-2">
              LLM Rubric
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
              Keyword
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

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
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
    </aside>
  )
}

export default PolicyBuilderModal
