/**
 * =============================================================================
 * File: SettingsHeader.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Page title + description for a Settings section.
 * Responsibilities:
 *   - Render consistent Scholarly Precision section header
 * Dependencies:
 *   - None
 * Public Exports:
 *   - SettingsHeader
 * Database/Table: N/A
 * Related Modules: features/settings/SettingsLayout.tsx
 * Important Notes: Keep quiet — content area is the focus.
 * =============================================================================
 */

type Props = {
  title: string;
  description: string;
  /** Optional trailing actions (e.g. Invite member). */
  actions?: React.ReactNode;
};

export function SettingsHeader({ title, description, actions }: Props) {
  return (
    <div className="flex flex-col gap-4 border-b border-border-default pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <p className="text-caption font-medium text-accent-primary">Cài đặt</p>
        <h1 className="mt-1 text-h1 text-primary">{title}</h1>
        <p className="mt-1 max-w-2xl text-body-sm text-secondary">{description}</p>
      </div>
      {actions ? <div className="shrink-0">{actions}</div> : null}
    </div>
  );
}
