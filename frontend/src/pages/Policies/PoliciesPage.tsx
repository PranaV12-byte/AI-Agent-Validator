import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import type { Policy, PolicyCreatePayload } from "../../types/api"
import {
  createPolicy,
  deletePolicy,
  fetchPolicies,
  updatePolicy,
} from "../../services/policyService"
import DeleteConfirmationModal from "./components/DeleteConfirmationModal"
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

  const savingRef = useRef(false)
  const [policyToDelete, setPolicyToDelete] = useState<Policy | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

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
    if (savingRef.current) return
    savingRef.current = true
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
      savingRef.current = false
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

      <PolicyBuilderModal
        mode={builderMode}
        policy={selectedPolicy}
        isOpen={isBuilderOpen}
        isSaving={isSaving}
        onClose={() => setIsBuilderOpen(false)}
        onSave={handleSave}
      />

      <DeleteConfirmationModal
        policy={policyToDelete}
        isDeleting={isDeleting}
        onCancel={() => setPolicyToDelete(null)}
        onConfirm={handleDeleteConfirm}
      />
    </>
  )
}

export default PoliciesPage
