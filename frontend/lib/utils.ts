/**
 * =============================================================================
 * File: utils.ts
 * Module/Service: Web App
 * Layer: UI
 * Purpose: Shared className helper for shadcn/ui components.
 * Responsibilities:
 *   - Merge Tailwind class names via clsx + tailwind-merge
 * Dependencies:
 *   - clsx, tailwind-merge
 * Public Exports:
 *   - cn
 * Database/Table: N/A
 * Related Modules: components/ui (shadcn)
 * Important Notes: Required by shadcn/ui init.
 * =============================================================================
 */

import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
