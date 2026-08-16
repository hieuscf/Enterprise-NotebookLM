/**
 * =============================================================================
 * File: reports.api.ts
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Typed calls to /workspaces/{id}/reports (FR9 / UC8).
 * Responsibilities:
 *   - list / create / get / delete Reports; download export binary
 * Dependencies:
 *   - lib/api-client (apiFetch, parseApiError)
 * Public Exports:
 *   - listReports, createReport, getReport, deleteReport, downloadReportExport
 * Database/Table: N/A
 * Related Modules: hooks/useReports, features/reports/*
 * Important Notes: POST returns 202 with status=pending — FE must poll.
 *   GET detail may include structured preview (CMP-25). Do not download
 *   export merely to render the preview.
 * =============================================================================
 */

import { apiFetch, parseApiError } from "@/lib/api-client";
import type { Report, ReportCreateRequest } from "@/types/reports";

export async function listReports(
  workspaceId: string,
  params?: { page?: number; pageSize?: number },
): Promise<Report[]> {
  const page = params?.page ?? 1;
  const pageSize = params?.pageSize ?? 20;
  const qs = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  const response = await apiFetch(
    `/workspaces/${workspaceId}/reports?${qs.toString()}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Report[];
}

export async function createReport(
  workspaceId: string,
  body: ReportCreateRequest,
): Promise<Report> {
  const response = await apiFetch(`/workspaces/${workspaceId}/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: body.title,
      export_format: body.export_format,
      items: body.items.map((item) => ({
        source_type: item.source_type,
        source_id: item.source_id,
        order_index: item.order_index,
      })),
    }),
  });
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Report;
}

export async function getReport(
  workspaceId: string,
  reportId: string,
): Promise<Report> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/reports/${reportId}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Report;
}

export async function deleteReport(
  workspaceId: string,
  reportId: string,
): Promise<void> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/reports/${reportId}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw await parseApiError(response);
}

export type ReportExportDownload = {
  blob: Blob;
  filename: string;
  contentType: string;
};

/** GET .../export — binary file for browser download. */
export async function downloadReportExport(
  workspaceId: string,
  reportId: string,
): Promise<ReportExportDownload> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/reports/${reportId}/export`,
    { headers: { Accept: "*/*" } },
  );
  if (!response.ok) throw await parseApiError(response);

  const contentType =
    response.headers.get("Content-Type") ?? "application/octet-stream";
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const matched = /filename="?([^";]+)"?/i.exec(disposition);
  const filename = matched?.[1]?.trim() || `report_${reportId}`;
  const blob = await response.blob();
  return { blob, filename, contentType };
}
