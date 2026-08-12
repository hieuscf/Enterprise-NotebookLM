/**
 * =============================================================================
 * File: AISettings.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: High-level AI response, citation, and knowledge-source preferences.
 * Responsibilities:
 *   - Persist preferences device-locally (no preferences API in OpenAPI)
 *   - Avoid exposing infrastructure / credentials
 * Dependencies:
 *   - preferences.ts, Settings* components, useToasts
 * Public Exports:
 *   - AISettings
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/settings/ai/page.tsx
 * Important Notes: Integration point for future preferences API is preferences.ts.
 * =============================================================================
 */

"use client";

import { useEffect, useState } from "react";

import { ToastStack } from "@/components/ui/toast";
import {
  loadPreferences,
  updatePreferences,
  type KnowledgeSourcePreferences,
  type ResponseStylePreference,
  type UserPreferences,
} from "@/features/settings/preferences";
import { SettingsHeader } from "@/features/settings/SettingsHeader";
import { SettingsLayout } from "@/features/settings/SettingsLayout";
import { SettingsRow } from "@/features/settings/SettingsRow";
import { SettingsSection } from "@/features/settings/SettingsSection";
import { SettingsSwitch } from "@/features/settings/SettingsSwitch";
import { useSettingsWorkspace } from "@/features/settings/useSettingsWorkspace";
import { useAuth } from "@/hooks/useAuth";
import { useToasts } from "@/hooks/useToasts";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
};

const RESPONSE_STYLES: {
  id: ResponseStylePreference;
  label: string;
  description: string;
}[] = [
  {
    id: "concise",
    label: "Ngắn gọn",
    description: "Trả lời súc tích, ưu tiên kết luận chính.",
  },
  {
    id: "balanced",
    label: "Cân bằng",
    description:
      "Trả lời ngắn gọn nhưng giữ đủ ngữ cảnh và bằng chứng hỗ trợ.",
  },
  {
    id: "detailed",
    label: "Chi tiết",
    description: "Trả lời đầy đủ hơn với giải thích và trích dẫn mở rộng.",
  },
];

const SOURCE_ROWS: {
  key: keyof KnowledgeSourcePreferences;
  label: string;
  description: string;
}[] = [
  {
    key: "knowledgeGraph",
    label: "Knowledge Graph",
    description: "Quan hệ thực thể trong Workspace.",
  },
  {
    key: "vectorSearch",
    label: "Vector Search",
    description: "Tìm kiếm ngữ nghĩa trên tài liệu.",
  },
  {
    key: "fullTextSearch",
    label: "Full-text Search",
    description: "Tìm kiếm toàn văn (BM25).",
  },
];

export function AISettings({ workspaceId }: Props) {
  const { user } = useAuth();
  const { workspace } = useSettingsWorkspace(workspaceId);
  const { toasts, dismiss, pushSuccess } = useToasts();
  const [prefs, setPrefs] = useState<UserPreferences | null>(null);

  useEffect(() => {
    setPrefs(loadPreferences());
  }, []);

  function persist(next: UserPreferences, message = "Đã cập nhật tuỳ chọn.") {
    setPrefs(next);
    updatePreferences(next);
    pushSuccess(message);
  }

  return (
    <SettingsLayout
      workspaceId={workspaceId}
      active="ai"
      user={user}
      workspaceName={workspace?.name}
    >
      <SettingsHeader
        title="AI & Retrieval"
        description="Kiểm soát cách câu trả lời AI sử dụng tri thức Workspace."
      />

      <p className="mb-2 max-w-2xl text-caption text-tertiary">
        Tuỳ chọn được lưu trên thiết bị này. Chưa đồng bộ máy chủ — hợp đồng API
        hiện chưa có endpoint preferences.
      </p>

      <SettingsSection title="Phong cách trả lời">
        {!prefs ? null : (
          <div className="flex max-w-xl flex-col gap-2" role="radiogroup" aria-label="Phong cách trả lời">
            {RESPONSE_STYLES.map((style) => {
              const selected = prefs.responseStyle === style.id;
              return (
                <label
                  key={style.id}
                  className={cn(
                    "flex cursor-pointer gap-3 rounded-md border px-3.5 py-3 transition-colors",
                    selected
                      ? "border-accent-primary/40 bg-accent-primary-soft/40"
                      : "border-border-default hover:bg-elevated/60",
                  )}
                >
                  <input
                    type="radio"
                    name="response-style"
                    value={style.id}
                    checked={selected}
                    onChange={() =>
                      persist({ ...prefs, responseStyle: style.id })
                    }
                    className="mt-1 accent-[var(--accent-primary)]"
                  />
                  <span>
                    <span className="block text-body-sm font-medium text-primary">
                      {style.label}
                    </span>
                    <span className="mt-0.5 block text-caption text-tertiary">
                      {style.description}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        )}
      </SettingsSection>

      <SettingsSection
        title="Tuỳ chọn trích dẫn"
        description="Trích dẫn kết nối câu trả lời với nội dung nguồn có thể kiểm chứng trong Workspace."
      >
        {!prefs ? null : (
          <div className="max-w-2xl divide-y divide-border-default">
            <SettingsRow
              label="Hiển thị trích dẫn trong câu trả lời AI"
              htmlFor="cite-show"
            >
              <SettingsSwitch
                id="cite-show"
                label="Hiển thị trích dẫn trong câu trả lời AI"
                checked={prefs.citations.showInAnswers}
                onCheckedChange={(checked) =>
                  persist({
                    ...prefs,
                    citations: { ...prefs.citations, showInAnswers: checked },
                  })
                }
              />
            </SettingsRow>
            <SettingsRow
              label="Mở nguồn khi chọn trích dẫn"
              htmlFor="cite-open"
            >
              <SettingsSwitch
                id="cite-open"
                label="Mở nguồn khi chọn trích dẫn"
                checked={prefs.citations.openSourceOnSelect}
                onCheckedChange={(checked) =>
                  persist({
                    ...prefs,
                    citations: {
                      ...prefs.citations,
                      openSourceOnSelect: checked,
                    },
                  })
                }
              />
            </SettingsRow>
            <SettingsRow
              label="Tô sáng đoạn được trích trong tài liệu"
              htmlFor="cite-highlight"
            >
              <SettingsSwitch
                id="cite-highlight"
                label="Tô sáng đoạn được trích trong tài liệu"
                checked={prefs.citations.highlightCitedText}
                onCheckedChange={(checked) =>
                  persist({
                    ...prefs,
                    citations: {
                      ...prefs.citations,
                      highlightCitedText: checked,
                    },
                  })
                }
              />
            </SettingsRow>
          </div>
        )}
      </SettingsSection>

      <SettingsSection
        title="Nguồn tri thức"
        description="AI tìm kiến thức ở đâu trong Workspace — không phải cấu hình hạ tầng nội bộ."
      >
        {!prefs ? null : (
          <div className="max-w-2xl divide-y divide-border-default">
            {SOURCE_ROWS.map((row) => (
              <SettingsRow
                key={row.key}
                label={row.label}
                description={row.description}
                htmlFor={`source-${row.key}`}
              >
                <SettingsSwitch
                  id={`source-${row.key}`}
                  label={row.label}
                  checked={prefs.knowledgeSources[row.key]}
                  onCheckedChange={(checked) =>
                    persist({
                      ...prefs,
                      knowledgeSources: {
                        ...prefs.knowledgeSources,
                        [row.key]: checked,
                      },
                    })
                  }
                />
              </SettingsRow>
            ))}
          </div>
        )}
      </SettingsSection>

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </SettingsLayout>
  );
}
