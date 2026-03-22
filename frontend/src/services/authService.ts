import { apiClient } from "./apiClient"
import type {
  AuthResponse,
  RegenerateApiKeyResponse,
  TenantProfile,
} from "../types/api"

type LoginPayload = {
  email: string
  password: string
}

export async function loginRequest(payload: LoginPayload): Promise<AuthResponse> {
  const response = await apiClient.post<AuthResponse>("/auth/login", payload)
  return response.data
}

export async function fetchTenantProfile(): Promise<TenantProfile> {
  const response = await apiClient.get<TenantProfile>("/auth/me")
  return response.data
}

export async function regenerateApiKeyRequest(): Promise<RegenerateApiKeyResponse> {
  const response = await apiClient.post<RegenerateApiKeyResponse>(
    "/auth/regenerate-key",
  )
  return response.data
}
