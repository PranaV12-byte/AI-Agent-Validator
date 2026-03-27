import type { Policy } from "../../../types/api"
import { ShieldAlert } from "lucide-react"

type PolicyListProps = {
  policies: Policy[]
  isLoading: boolean
  error: string | null
  onCreate: () => void
  onEdit: (policy: Policy) => void
  onDelete: (policy: Policy) => void
  onToggle: (policy: Policy) => void
}

const RULE_TYPE_LABELS: Record<string, string> = {
  pii_redaction: "Hide Personal Info",
  prompt_injection: "Block Manipulation",
  keyword: "Word Match",
  regex_match: "Pattern Match",
  llm_eval: "AI Content Check",
  semantic: "Meaning Match",
}

function formatRuleType(ruleType: string): string {
  return RULE_TYPE_LABELS[ruleType] ?? ruleType.replaceAll("_", " ")
}

function PolicyList({
  policies,
  isLoading,
  error,
  onCreate,
  onEdit,
  onDelete,
  onToggle,
}: PolicyListProps) {
  if (error) {
    return (
      <section className="bg-card-bg border border-border-color rounded-2xl p-6">
        <p className="text-brand-red">Unable to load policies right now.</p>
      </section>
    )
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold mb-1">Protection Rules</h1>
          <p className="text-text-muted">Set up rules to keep your AI safe for your customers.</p>
        </div>
        <button
          type="button"
          onClick={onCreate}
          className="px-4 py-2 rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green hover:bg-brand-green/20"
        >
          Add a Rule
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {isLoading
          ? Array.from({ length: 6 }).map((_, index) => (
              <div key={`policy-skeleton-${index}`} className="bg-card-bg border border-border-color rounded-2xl p-5">
                <div className="h-5 w-40 bg-border-color/70 rounded animate-pulse mb-4" />
                <div className="h-4 w-24 bg-border-color/70 rounded animate-pulse mb-3" />
                <div className="h-4 w-full bg-border-color/70 rounded animate-pulse" />
              </div>
            ))
          : policies.length === 0
            ? (
              <div className="md:col-span-2 xl:col-span-3 bg-card-bg border border-border-color rounded-2xl p-10 text-center">
                <ShieldAlert className="w-10 h-10 text-text-muted mx-auto mb-4" />
                <h3 className="text-lg font-semibold mb-2">No rules set up yet</h3>
                <p className="text-text-muted mb-5">
                  Add your first rule to start protecting your AI assistant from harmful or inappropriate messages.
                </p>
                <button
                  type="button"
                  onClick={onCreate}
                  className="px-4 py-2 rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green hover:bg-brand-green/20"
                >
                  Add Your First Rule
                </button>
              </div>
              )
          : policies.map((policy) => (
              <article key={policy.id} className="bg-card-bg border border-border-color rounded-2xl p-5">
                <div className="flex items-start justify-between gap-4 mb-4">
                  <div>
                    <h2 className="text-lg font-semibold">{policy.name}</h2>
                    <p className="text-xs uppercase text-text-muted tracking-wide mt-1">
                      {formatRuleType(policy.rule_type)}
                    </p>
                  </div>
                  <label className="inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={policy.is_enabled}
                      onChange={() => onToggle(policy)}
                      className="sr-only"
                    />
                    <span
                      className={[
                        "w-11 h-6 rounded-full border transition-colors relative",
                        policy.is_enabled
                          ? "bg-brand-green/20 border-brand-green/40"
                          : "bg-border-color border-border-color",
                      ].join(" ")}
                    >
                      <span
                        className={[
                          "absolute top-0.5 w-5 h-5 bg-white rounded-full transition-transform",
                          policy.is_enabled ? "translate-x-5" : "translate-x-0.5",
                        ].join(" ")}
                      />
                    </span>
                  </label>
                </div>

                <p className="text-sm text-text-muted min-h-10">
                  {policy.description || "No description provided."}
                </p>

                <div className="flex items-center justify-between mt-5">
                  <button
                    type="button"
                    onClick={() => onEdit(policy)}
                    className="text-sm text-text-muted hover:text-white"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(policy)}
                    className="text-sm text-brand-red hover:text-red-300"
                  >
                    Delete
                  </button>
                </div>
              </article>
            ))}
      </div>
    </section>
  )
}

export default PolicyList
