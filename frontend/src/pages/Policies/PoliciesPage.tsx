import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import type { Policy, PolicyCreatePayload } from "../../types/api"
import {
  createPolicy,
  deletePolicy,
  fetchPolicies,
  updatePolicy,
} from "../../services/policyService"
import DeleteConfirmationModal from "./components/DeleteConfirmationModal"
import PolicyPage from "./PolicyPage"
import PolicyBuilderModal from "./components/PolicyBuilderModal"
import PolicyList from "./components/PolicyList"

function PoliciesPage() {
  const [policies, setPolicies] = useState<Policy[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null)
  const [builderMode, setBuilderMode] = useState<"create" | "edit">("create")
  const [isBuilderOpen, setIsBuilderOpen] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const [policyToDelete, setPolicyToDelete] = useState<Policy | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [activeTab, setActiveTab] = useState<"rules" | "config">("rules")

  const loadPolicies = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await fetchPolicies()
      setPolicies(response.policies)
    } catch {
      setError("Failed to load policies")
      toast.error("Failed to load policies")
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadPolicies()
  }, [loadPolicies])

  async function handleSave(payload: PolicyCreatePayload) {
    setIsSaving(true)

    try {
      if (builderMode === "create") {
        await createPolicy(payload)
        toast.success("Policy created successfully")
      } else if (selectedPolicy) {
        await updatePolicy(selectedPolicy.id, payload)
        toast.success("Policy updated successfully")
      }

      setIsBuilderOpen(false)
      setSelectedPolicy(null)
      await loadPolicies()
    } catch {
      toast.error("Could not save policy")
    } finally {
      setIsSaving(false)
    }
  }

  async function handleDeleteConfirm() {
    if (!policyToDelete) {
      return
    }

    setIsDeleting(true)
    try {
      await deletePolicy(policyToDelete.id)
      setPolicyToDelete(null)
      await loadPolicies()
      toast.success("Policy deleted")
    } catch {
      toast.error("Could not delete policy")
    } finally {
      setIsDeleting(false)
    }
  }

  async function handleToggle(policy: Policy) {
    try {
      await updatePolicy(policy.id, { is_enabled: !policy.is_enabled })
      await loadPolicies()
      toast.success(
        !policy.is_enabled ? "Policy enabled" : "Policy disabled",
      )
    } catch {
      toast.error("Could not update policy state")
    }
  }

  return (
    <>
      <div className="flex items-center gap-2 mb-4">
        <button
          type="button"
          onClick={() => setActiveTab("rules")}
          className={[
            "px-3 py-2 rounded-lg border text-sm",
            activeTab === "rules"
              ? "border-brand-green/40 text-brand-green bg-brand-green/10"
              : "border-border-color text-text-muted hover:text-white",
          ].join(" ")}
        >
          My Protection Rules
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("config")}
          className={[
            "px-3 py-2 rounded-lg border text-sm",
            activeTab === "config"
              ? "border-brand-green/40 text-brand-green bg-brand-green/10"
              : "border-border-color text-text-muted hover:text-white",
          ].join(" ")}
        >
          Settings
        </button>
      </div>

      {activeTab === "config" ? <PolicyPage /> : null}

      {activeTab === "rules" ? (
      <PolicyList
        policies={policies}
        isLoading={isLoading}
        error={error}
        onCreate={() => {
          setBuilderMode("create")
          setSelectedPolicy(null)
          setIsBuilderOpen(true)
        }}
        onEdit={(policy) => {
          setBuilderMode("edit")
          setSelectedPolicy(policy)
          setIsBuilderOpen(true)
        }}
        onDelete={(policy) => setPolicyToDelete(policy)}
        onToggle={(policy) => void handleToggle(policy)}
      />
      ) : null}

      {activeTab === "rules" ? (
        <PolicyBuilderModal
          mode={builderMode}
          policy={selectedPolicy}
          isOpen={isBuilderOpen}
          isSaving={isSaving}
          onClose={() => setIsBuilderOpen(false)}
          onSave={handleSave}
        />
      ) : null}

      {activeTab === "rules" ? (
        <DeleteConfirmationModal
          policy={policyToDelete}
          isDeleting={isDeleting}
          onCancel={() => setPolicyToDelete(null)}
          onConfirm={handleDeleteConfirm}
        />
      ) : null}
    </>
  )
}

export default PoliciesPage
