/**
 * Node-side smoke checks for Admin Users pure helpers (no Jest/RTL yet).
 * Mirrors features/admin/admin-users.ts + CreateUserDialog validation — keep in sync.
 * Run: node scripts/test-admin-users.mjs
 */

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  } else {
    console.log("OK:", msg);
  }
}

function uniqueRoles(memberships) {
  const order = ["admin", "editor", "viewer"];
  const present = new Set(memberships.map((m) => m.role));
  return order.filter((r) => present.has(r));
}

function compactWorkspaceNames(memberships, maxVisible = 2) {
  const names = memberships.map((m) => m.workspace_name);
  if (names.length <= maxVisible) return { visible: names, overflow: 0 };
  return { visible: names.slice(0, maxVisible), overflow: names.length - maxVisible };
}

function earliestJoinedAt(memberships) {
  if (memberships.length === 0) return null;
  let earliest = memberships[0].joined_at;
  for (const m of memberships) {
    if (m.joined_at < earliest) earliest = m.joined_at;
  }
  return earliest;
}

function filterAdminUsers(users, filters) {
  const q = filters.searchQuery.trim().toLowerCase();
  return users.filter((user) => {
    if (q) {
      const haystack = `${user.email} ${user.full_name}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    if (filters.workspaceId) {
      if (!user.memberships.some((m) => m.workspace_id === filters.workspaceId)) {
        return false;
      }
    }
    if (filters.role) {
      if (!user.memberships.some((m) => m.role === filters.role)) return false;
    }
    return true;
  });
}

function paginateItems(items, page, pageSize) {
  const start = (page - 1) * pageSize;
  return items.slice(start, start + pageSize);
}

function initialsFromEmail(email) {
  const local = email.split("@")[0]?.trim() ?? "";
  if (!local) return "?";
  const parts = local.split(/[._\-\s]+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
  }
  return local.slice(0, 2).toUpperCase();
}

function validateCreateUserForm(input) {
  const errors = {};
  const full_name = input.full_name.trim();
  const email = input.email.trim().toLowerCase();
  const password = input.password;
  const confirm_password = input.confirm_password;
  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!full_name) errors.full_name = "Full name is required.";
  if (!email) errors.email = "Email is required.";
  else if (!EMAIL_RE.test(email)) errors.email = "Enter a valid email address.";
  if (!password) errors.password = "Password is required.";
  if (!confirm_password) errors.confirm_password = "Confirm your password.";
  else if (password && confirm_password !== password) {
    errors.confirm_password = "Passwords do not match.";
  }
  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return { ok: true, values: { full_name, email, password } };
}

const sample = [
  {
    user_id: "u1",
    email: "alice@example.com",
    full_name: "Alice Nguyen",
    memberships: [
      {
        workspace_id: "w1",
        workspace_name: "Finance",
        role: "admin",
        joined_at: "2026-01-02T00:00:00Z",
      },
      {
        workspace_id: "w2",
        workspace_name: "Engineering",
        role: "editor",
        joined_at: "2026-01-01T00:00:00Z",
      },
      {
        workspace_id: "w3",
        workspace_name: "HR",
        role: "viewer",
        joined_at: "2026-02-01T00:00:00Z",
      },
    ],
  },
  {
    user_id: "u2",
    email: "bob@example.com",
    full_name: "Bob Tran",
    memberships: [
      {
        workspace_id: "w1",
        workspace_name: "Finance",
        role: "viewer",
        joined_at: "2026-03-01T00:00:00Z",
      },
    ],
  },
];

assert(
  JSON.stringify(uniqueRoles(sample[0].memberships)) ===
    JSON.stringify(["admin", "editor", "viewer"]),
  "uniqueRoles orders admin → editor → viewer",
);

const compact = compactWorkspaceNames(sample[0].memberships);
assert(compact.visible.length === 2 && compact.overflow === 1, "compactWorkspaceNames +1 more");

assert(
  earliestJoinedAt(sample[0].memberships) === "2026-01-01T00:00:00Z",
  "earliestJoinedAt picks oldest membership",
);

assert(
  filterAdminUsers(sample, { searchQuery: "bob", workspaceId: "", role: "" }).length === 1,
  "search filters by email",
);
assert(
  filterAdminUsers(sample, { searchQuery: "alice nguyen", workspaceId: "", role: "" }).length === 1,
  "search filters by full_name",
);
assert(
  filterAdminUsers(sample, { searchQuery: "", workspaceId: "w2", role: "" })[0]?.user_id === "u1",
  "workspace filter keeps users with that membership",
);
assert(
  filterAdminUsers(sample, { searchQuery: "", workspaceId: "", role: "admin" }).length === 1,
  "role filter = at least one matching membership",
);
assert(
  filterAdminUsers(sample, { searchQuery: "zzz", workspaceId: "", role: "" }).length === 0,
  "no match returns empty",
);

assert(paginateItems(sample, 1, 1).length === 1, "paginateItems page 1");
assert(paginateItems(sample, 2, 1)[0]?.user_id === "u2", "paginateItems page 2");
assert(initialsFromEmail("nguyen.van.a@example.com") === "NV", "initialsFromEmail multi-part");
assert(initialsFromEmail("alice@example.com") === "AL", "initialsFromEmail single local");

assert(
  !validateCreateUserForm({
    full_name: "",
    email: "a@b.com",
    password: "x",
    confirm_password: "x",
  }).ok,
  "create validation requires full_name",
);
assert(
  !validateCreateUserForm({
    full_name: "A",
    email: "bad",
    password: "x",
    confirm_password: "x",
  }).ok,
  "create validation rejects invalid email",
);
assert(
  !validateCreateUserForm({
    full_name: "A",
    email: "a@b.com",
    password: "x",
    confirm_password: "y",
  }).ok,
  "create validation rejects password mismatch",
);
const okCreate = validateCreateUserForm({
  full_name: "  New User ",
  email: " New@Example.COM ",
  password: "secret",
  confirm_password: "secret",
});
assert(okCreate.ok && okCreate.values.email === "new@example.com", "create validation normalizes email");
assert(okCreate.values.full_name === "New User", "create validation trims full_name");
assert(
  !("confirm_password" in okCreate.values),
  "confirm_password is UI-only and not in submit payload",
);

if (process.exitCode) {
  console.error("\nAdmin users helper tests failed.");
  process.exit(1);
}
console.log("\nAll admin users helper tests passed.");
