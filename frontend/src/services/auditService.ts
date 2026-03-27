import { apiClient } from "./apiClient"
import type { AuditListResponse } from "../types/api"

type FetchAuditLogsParams = {
  page?: number
  page_size?: number
  action?: "BLOCKED" | "ALLOWED" | "REDACTED"
  start_date?: string
  end_date?: string
}

export async function fetchAuditLogs(
  params: FetchAuditLogsParams = {},
): Promise<AuditListResponse> {
  const { page = 1, page_size = 20, action, start_date, end_date } = params
  const offset = Math.max(0, (page - 1) * page_size)

  const response = await apiClient.get<AuditListResponse>("/audit/", {
    params: {
      limit: page_size,
      offset,
      action,
      start_date: start_date || undefined,
      end_date: end_date || undefined,
    },
  })

  return response.data
}
