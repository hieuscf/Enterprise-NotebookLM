/**
 * =============================================================================
 * File: test-rbac.mjs
 * Module/Service: Auth (Web App) — Platform + Workspace RBAC
 * Layer: UI
 * Purpose: Lightweight assertions for frontend permission helpers.
 * Responsibilities:
 *   - canAccessAdmin only for platform_role === manage
 *   - Workspace admin does not grant Admin Console
 * Public Exports: N/A (script)
 * =============================================================================
 */

import assert from "node:assert/strict";

function canAccessAdmin(user) {
  return user?.platform_role === "manage";
}

function getWorkspaceRole(user, workspaceId) {
  if (!user || !workspaceId) return null;
  return user.workspaces.find((w) => w.workspace_id === workspaceId)?.role ?? null;
}

function canManageMembers(user, workspaceId) {
  return getWorkspaceRole(user, workspaceId) === "admin";
}

const finance = "finance-id";
const hr = "hr-id";

const manageUser = {
  id: "1",
  email: "m@ex.com",
  full_name: "Manage",
  platform_role: "manage",
  workspaces: [{ workspace_id: finance, role: "viewer" }],
};

const workspaceAdmin = {
  id: "2",
  email: "a@ex.com",
  full_name: "WS Admin",
  platform_role: null,
  workspaces: [
    { workspace_id: finance, role: "admin" },
    { workspace_id: hr, role: "viewer" },
  ],
};

const editor = {
  id: "3",
  email: "e@ex.com",
  full_name: "Editor",
  platform_role: null,
  workspaces: [{ workspace_id: finance, role: "editor" }],
};

const viewer = {
  id: "4",
  email: "v@ex.com",
  full_name: "Viewer",
  platform_role: null,
  workspaces: [{ workspace_id: finance, role: "viewer" }],
};

assert.equal(canAccessAdmin(manageUser), true);
assert.equal(canAccessAdmin(workspaceAdmin), false);
assert.equal(canAccessAdmin(editor), false);
assert.equal(canAccessAdmin(viewer), false);
assert.equal(canAccessAdmin(null), false);

assert.equal(canManageMembers(workspaceAdmin, finance), true);
assert.equal(canManageMembers(workspaceAdmin, hr), false);
assert.equal(canManageMembers(editor, finance), false);
assert.equal(canManageMembers(viewer, finance), false);
assert.equal(canManageMembers(manageUser, finance), false);

console.log("test-rbac.mjs: ok");
