import { apiClient } from "./apiClient"
import type { PolicyConfig, PolicyConfigUpdatePayload } from "../types/api"

export async function fetchPolicyConfig(): Promise<PolicyConfig> {
  const response = await apiClient.get<PolicyConfig>("/policies/config")
  return response.data
}

export async function updatePolicyConfig(
  payload: PolicyConfigUpdatePayload,
): Promise<PolicyConfig> {
  const response = await apiClient.put<PolicyConfig>("/policies/config", payload)
  return response.data
}
