import { apiClient } from "./apiClient"
import type { AuditListResponse } from "../types/api"

type FetchAuditLogsParams = {
  page?: number
  page_size?: number
  action?: "BLOCKED" | "ALLOWED" | "REDACTED"
}

export async function fetchAuditLogs(
  params: FetchAuditLogsParams = {},
): Promise<AuditListResponse> {
  const { page = 1, page_size = 20, action } = params
  const offset = Math.max(0, (page - 1) * page_size)

  const response = await apiClient.get<AuditListResponse["logs"]>("/audit/", {
    params: {
      limit: page_size,
      offset,
      action,
    },
  })

  return {
    logs: response.data,
    total: response.data.length === page_size ? offset + response.data.length + 1 : offset + response.data.length,
    page,
    page_size,
  }
}
