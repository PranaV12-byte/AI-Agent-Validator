import axios from "axios"
import type { AuthAwareRequestConfig } from "./apiClient"
import { apiClient } from "./apiClient"

export type ProtectedChatStatus =
  | "allowed"
  | "redacted"
  | "blocked"
  | "evaluation_failed"
  | "provider_unavailable"
  | "service_unavailable"
  | "busy"

export type ProtectedChatResponse = {
  conversation_id: string
  status: ProtectedChatStatus
  answer: string | null
  fallback_message: string | null
  error_code: string | null
  input_redacted: boolean
  output_redacted: boolean
  policy_version: number
  audit_ids: string[]
}

export type ProtectedChatReadiness = {
  ready: boolean
  error_code: string | null
  model: string
}

function isProtectedChatResponse(value: unknown): value is ProtectedChatResponse {
  if (typeof value !== "object" || value === null) return false
  const candidate = value as Partial<ProtectedChatResponse>
  return (
    typeof candidate.status === "string" &&
    typeof candidate.conversation_id === "string" &&
    typeof candidate.policy_version === "number" &&
    Array.isArray(candidate.audit_ids)
  )
}

export async function fetchProtectedChatReadiness(
  signal?: AbortSignal,
): Promise<ProtectedChatReadiness> {
  const config: AuthAwareRequestConfig = {
    signal,
    timeout: 15000,
    _disableRetries: true,
  }
  const response = await apiClient.get<ProtectedChatReadiness>(
    "/demo/protected-chat/readiness",
    config,
  )
  return response.data
}

export async function submitProtectedChat(
  message: string,
  signal: AbortSignal,
): Promise<ProtectedChatResponse> {
  const config: AuthAwareRequestConfig = {
    signal,
    timeout: 85000,
    _disableRetries: true,
  }
  try {
    const response = await apiClient.post<ProtectedChatResponse>(
      "/demo/protected-chat",
      { message },
      config,
    )
    return response.data
  } catch (error) {
    if (axios.isAxiosError(error) && isProtectedChatResponse(error.response?.data)) {
      return error.response.data
    }
    throw error
  }
}
