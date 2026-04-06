import { apiClient } from "./apiClient"
import type {
  AuthResponse,
  ForgotPasswordResponse,
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

export async function requestPasswordReset(
  email: string,
): Promise<ForgotPasswordResponse> {
  const response = await apiClient.post<ForgotPasswordResponse>(
    "/auth/forgot-password",
    { email },
  )
  return response.data
}

export async function confirmPasswordReset(
  token: string,
  newPassword: string,
): Promise<void> {
  await apiClient.post("/auth/reset-password", {
    token,
    new_password: newPassword,
  })
}

export async function refreshTokenRequest(refreshToken: string): Promise<AuthResponse> {
  const response = await apiClient.post<AuthResponse>("/auth/refresh", {
    refresh_token: refreshToken,
  }, { _skipProactiveRefresh: true } as object)
  return response.data
}

export async function logoutRequest(refreshToken: string | null = null): Promise<void> {
  await apiClient.post(
    "/auth/logout",
    refreshToken ? { refresh_token: refreshToken } : undefined,
    { _skipProactiveRefresh: true } as object,
  )
}

export async function verifyEmail(token: string): Promise<{ message: string }> {
  const response = await apiClient.post<{ message: string }>("/auth/verify-email", { token })
  return response.data
}

export async function resendVerification(email: string): Promise<{ message: string }> {
  const response = await apiClient.post<{ message: string }>("/auth/resend-verification", { email })
  return response.data
}

export async function changePasswordRequest(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await apiClient.post("/auth/change-password", {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

export async function updateProfileRequest(payload: {
  company_name?: string
  email?: string
}): Promise<TenantProfile> {
  const response = await apiClient.put<TenantProfile>("/auth/me", payload)
  return response.data
}
