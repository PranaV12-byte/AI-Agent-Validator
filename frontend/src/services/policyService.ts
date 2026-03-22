import { apiClient } from "./apiClient"
import type {
  Policy,
  PolicyCreatePayload,
  PolicyListResponse,
  PolicyUpdatePayload,
} from "../types/api"

export async function fetchPolicies(): Promise<PolicyListResponse> {
  const response = await apiClient.get<PolicyListResponse>("/policies/")
  return response.data
}

export async function createPolicy(payload: PolicyCreatePayload): Promise<Policy> {
  const response = await apiClient.post<Policy>("/policies/", payload)
  return response.data
}

export async function updatePolicy(
  policyId: string,
  payload: PolicyUpdatePayload,
): Promise<Policy> {
  const response = await apiClient.put<Policy>(`/policies/${policyId}`, payload)
  return response.data
}

export async function deletePolicy(policyId: string): Promise<void> {
  await apiClient.delete(`/policies/${policyId}`)
}
