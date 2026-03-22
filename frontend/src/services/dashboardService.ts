import { apiClient } from "./apiClient"
import type {
  DashboardResponse,
  SafetyConfig,
  SafetyConfigUpdatePayload,
} from "../types/api"

export async function fetchDashboardStats(): Promise<DashboardResponse> {
  const response = await apiClient.get<DashboardResponse>("/dashboard/stats")
  return response.data
}

export async function fetchSafetyConfig(): Promise<SafetyConfig> {
  const response = await apiClient.get<SafetyConfig>("/dashboard/safety-config")
  return response.data
}

export async function updateSafetyConfig(
  payload: SafetyConfigUpdatePayload,
): Promise<SafetyConfig> {
  const response = await apiClient.put<SafetyConfig>("/dashboard/safety-config", payload)
  return response.data
}
