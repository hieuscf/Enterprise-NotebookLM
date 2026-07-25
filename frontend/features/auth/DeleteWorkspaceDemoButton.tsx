/**
 * =============================================================================
 * File: DeleteWorkspaceDemoButton.tsx
 * Module/Service: Auth / RBAC (Web App)
 * Layer: UI
 * Purpose: Demo of useWorkspaceRole — show "Xoá Workspace" only for admin.
 * Responsibilities:
 *   - Hide/disable delete control when role !== admin
 * Dependencies:
 *   - hooks/useWorkspaceRole
 * Public Exports:
 *   - DeleteWorkspaceDemoButton
 * Database/Table: N/A
 * Related Modules: Phase 1.3 will wire real DELETE; this is UI gate demo only
 * Important Notes: Backend RBAC remains authoritative — UI gate is convenience.
 * =============================================================================
 */

"use client";

import { useWorkspaceRole } from "@/hooks/useWorkspaceRole";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
};

export function DeleteWorkspaceDemoButton({ workspaceId }: Props) {
  const { isAdmin, loading, role } = useWorkspaceRole(workspaceId);

  if (loading) {
    return (
      <p className="text-body-sm text-tertiary">Đang tải quyền workspace…</p>
    );
  }

  if (!isAdmin) {
    return (
      <p className="text-body-sm text-secondary">
        Nút &quot;Xoá Workspace&quot; ẩn — role hiện tại:{" "}
        <span className="font-medium text-primary">{role ?? "không phải thành viên"}</span>
        {" "}(chỉ admin mới thấy).
      </p>
    );
  }

  return (
    <button
      type="button"
      className={cn(
        "rounded-md border border-border-default bg-danger-soft px-4 py-2",
        "text-body-sm font-medium text-danger",
        "hover:opacity-90",
      )}
      onClick={() => {
        // Demo only — real cascade delete lands in phase 1.3.
        window.alert(
          "Demo RBAC UI: bạn là admin nên thấy nút này. Xoá thật sẽ có ở giai đoạn 1.3.",
        );
      }}
    >
      Xoá Workspace
    </button>
  );
}
