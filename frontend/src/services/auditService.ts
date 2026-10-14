import { apiClient } from "./apiClient"
import type { AuditListResponse, AuditLog } from "../types/api"

type FetchAuditLogsParams = {
  page?: number
  page_size?: number
  action?: AuditLog["action"]
  start_date?: string
  end_date?: string
  search?: string
  review_status?: "open" | "resolved" | "unreviewed"
}

export async function fetchAuditLogs(
  params: FetchAuditLogsParams = {},
): Promise<AuditListResponse> {
  const { page = 1, page_size = 20, action, start_date, end_date, search, review_status } = params
  const offset = Math.max(0, (page - 1) * page_size)

  const response = await apiClient.get<AuditListResponse>("/audit/", {
    params: {
      limit: page_size,
      offset,
      action,
      start_date: start_date || undefined,
      end_date: end_date || undefined,
      search: search || undefined,
      review_status,
    },
  })

  return response.data
}

type ExportAuditLogsParams = {
  action?: AuditLog["action"]
  start_date?: string
  end_date?: string
  search?: string
  review_status?: "open" | "resolved" | "unreviewed"
}

export async function exportAuditLogs(params: ExportAuditLogsParams = {}): Promise<void> {
  const response = await apiClient.get<Blob>("/audit/export", {
    params: {
      action: params.action,
      start_date: params.start_date,
      end_date: params.end_date,
      search: params.search,
      review_status: params.review_status,
    },
    responseType: "blob",
  })
  const url = URL.createObjectURL(response.data)
  const link = document.createElement("a")
  link.href = url
  link.download = "safebot-audit-export.csv"
  link.click()
  URL.revokeObjectURL(url)
}
