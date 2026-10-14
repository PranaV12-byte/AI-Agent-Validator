import type { DecisionFeedback, DecisionFeedbackPayload, TestCase, TestCasePayload, TestRunResponse } from "../types/api"
import { apiClient } from "./apiClient"
import type { AuthAwareRequestConfig } from "./apiClient"

export async function fetchTestCases(signal?: AbortSignal): Promise<TestCase[]> {
  const response = await apiClient.get<{ cases: TestCase[]; limit: number }>("/test-lab/cases", { signal })
  return response.data.cases
}

export async function createTestCase(payload: TestCasePayload, sourceFeedbackId?: string): Promise<TestCase> {
  const path = sourceFeedbackId
    ? `/test-lab/feedback/${encodeURIComponent(sourceFeedbackId)}/cases`
    : "/test-lab/cases"
  const response = await apiClient.post<TestCase>(path, payload, { _disableRetries: true } as AuthAwareRequestConfig)
  return response.data
}

export async function updateTestCase(id: string, payload: TestCasePayload & { revision: number }): Promise<TestCase> {
  const response = await apiClient.put<TestCase>(`/test-lab/cases/${encodeURIComponent(id)}`, payload, {
    _disableRetries: true,
  } as AuthAwareRequestConfig)
  return response.data
}

export async function deleteTestCase(id: string): Promise<void> {
  await apiClient.delete(`/test-lab/cases/${encodeURIComponent(id)}`, { _disableRetries: true } as AuthAwareRequestConfig)
}

export async function runTestCases(caseIds?: string[]): Promise<TestRunResponse> {
  const response = await apiClient.post<TestRunResponse>("/test-lab/run", {
    case_ids: caseIds,
  }, { _disableRetries: true } as AuthAwareRequestConfig)
  return response.data
}

export async function fetchDecisionFeedback(auditLogId: string, signal?: AbortSignal): Promise<DecisionFeedback | null> {
  const response = await apiClient.get<DecisionFeedback | null>(
    `/audit/${encodeURIComponent(auditLogId)}/feedback`,
    { signal },
  )
  return response.data
}

export async function saveDecisionFeedback(
  auditLogId: string,
  payload: DecisionFeedbackPayload,
): Promise<DecisionFeedback> {
  const response = await apiClient.put<DecisionFeedback>(
    `/audit/${encodeURIComponent(auditLogId)}/feedback`,
    payload,
    { _disableRetries: true } as AuthAwareRequestConfig,
  )
  return response.data
}
