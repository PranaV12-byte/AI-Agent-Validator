import { apiClient } from "./apiClient"
import type { AuditListResponse, AuditLog } from "../types/api"

type FetchAuditLogsParams = {
  page?: number
  page_size?: number
  action?: AuditLog["action"]
  start_date?: string
  end_date?: string
  search?: string
}

export async function fetchAuditLogs(
  params: FetchAuditLogsParams = {},
): Promise<AuditListResponse> {
  const { page = 1, page_size = 20, action, start_date, end_date, search } = params
  const offset = Math.max(0, (page - 1) * page_size)

  const response = await apiClient.get<AuditListResponse>("/audit/", {
    params: {
      limit: page_size,
      offset,
      action,
      start_date: start_date || undefined,
      end_date: end_date || undefined,
      search: search || undefined,
    },
  })

  return response.data
}

type ExportAuditLogsParams = {
  action?: AuditLog["action"]
  start_date?: string
  end_date?: string
  search?: string
}

export async function exportAuditLogs(params: ExportAuditLogsParams = {}): Promise<void> {
  const response = await apiClient.get<Blob>("/audit/export", {
    params,
    responseType: "blob",
  })
  const url = URL.createObjectURL(response.data)
  const link = document.createElement("a")
  link.href = url
  link.download = "safebot-audit-export.csv"
  link.click()
  URL.revokeObjectURL(url)
}
