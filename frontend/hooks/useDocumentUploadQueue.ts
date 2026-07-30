/**
 * =============================================================================
 * File: useDocumentUploadQueue.ts
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Manage multi-file upload with bounded concurrency for the Upload
 *          page (FR2 / UC2) — POST /workspaces/{id}/documents per file, or
 *          POST .../documents/{documentId}/versions in "replace" mode
 *          (Part 2 — upload a new version for an existing document).
 * Responsibilities:
 *   - Hold job list (queued/uploading/processing/failed) + per-job progress
 *   - Enforce MAX_CONCURRENT_UPLOADS in-flight requests; rest wait as "queued"
 *   - Start the next queued job whenever a slot frees up
 *   - Route each job to the right endpoint based on its UploadTarget
 * Dependencies:
 *   - lib/api-client.uploadDocumentXhr, uploadDocumentVersionXhr
 *   - lib/upload-constraints
 * Public Exports:
 *   - useDocumentUploadQueue, type UploadJob, type UploadJobStatus
 *   - type StagedFile, type UploadTarget
 * Database/Table: documents, document_versions
 * Related Modules: features/documents/DocumentUploadDropzone, UploadJobCard,
 *   DocumentUploadView, DocumentVersionHistory
 * Important Notes: A job only reaches "processing" once the 202 response with
 *   a DocumentVersion is received — pipeline progress from there on is owned
 *   by usePipelineStatus/PipelineStatusTracker, not this hook.
 * =============================================================================
 */

"use client";

import { useCallback, useRef, useState } from "react";

import { ApiClientError, uploadDocumentVersionXhr, uploadDocumentXhr } from "@/lib/api-client";
import { MAX_CONCURRENT_UPLOADS } from "@/lib/upload-constraints";
import type { DocumentVersion } from "@/types/documents";

export type UploadJobStatus = "queued" | "uploading" | "processing" | "failed";

/** "new" creates a document (version 1); "replace" adds a version to an existing one. */
export type UploadTarget = { mode: "new" } | { mode: "replace"; documentId: string };

export type UploadJob = {
  clientId: string;
  file: File;
  title: string;
  target: UploadTarget;
  status: UploadJobStatus;
  progress: number;
  version: DocumentVersion | null;
  errorMessage: string | null;
};

export type StagedFile = { file: File; title: string };

let jobIdCounter = 0;

export function useDocumentUploadQueue(
  workspaceId: string,
  handlers?: {
    onUploaded?: (job: UploadJob) => void;
    onFailed?: (job: UploadJob) => void;
  },
) {
  const jobsRef = useRef<UploadJob[]>([]);
  const abortsRef = useRef<Map<string, () => void>>(new Map());
  const [jobs, setJobs] = useState<UploadJob[]>([]);

  const commit = useCallback(() => {
    setJobs([...jobsRef.current]);
  }, []);

  const patchJob = useCallback(
    (clientId: string, patch: Partial<UploadJob>) => {
      jobsRef.current = jobsRef.current.map((job) =>
        job.clientId === clientId ? { ...job, ...patch } : job,
      );
      commit();
    },
    [commit],
  );

  const pumpRef = useRef<() => void>(() => {});

  const startJob = useCallback(
    (job: UploadJob) => {
      patchJob(job.clientId, { status: "uploading", progress: 0, errorMessage: null });

      const onProgress = (percent: number) => patchJob(job.clientId, { progress: percent });
      const { promise, abort } =
        job.target.mode === "replace"
          ? uploadDocumentVersionXhr(workspaceId, job.target.documentId, job.file, onProgress)
          : uploadDocumentXhr(workspaceId, job.file, job.title, onProgress);
      abortsRef.current.set(job.clientId, abort);

      promise
        .then((version) => {
          abortsRef.current.delete(job.clientId);
          patchJob(job.clientId, { status: "processing", version, progress: 100 });
          const updated = jobsRef.current.find((j) => j.clientId === job.clientId);
          if (updated) handlers?.onUploaded?.(updated);
        })
        .catch((err) => {
          abortsRef.current.delete(job.clientId);
          const message =
            err instanceof ApiClientError
              ? err.message
              : "Tải lên thất bại, vui lòng thử lại.";
          patchJob(job.clientId, { status: "failed", errorMessage: message });
          const updated = jobsRef.current.find((j) => j.clientId === job.clientId);
          if (updated) handlers?.onFailed?.(updated);
        })
        .finally(() => {
          pumpRef.current();
        });
    },
    [workspaceId, patchJob, handlers],
  );

  const pump = useCallback(() => {
    const uploadingCount = jobsRef.current.filter((j) => j.status === "uploading").length;
    let freeSlots = MAX_CONCURRENT_UPLOADS - uploadingCount;
    if (freeSlots <= 0) return;

    for (const job of jobsRef.current) {
      if (freeSlots <= 0) break;
      if (job.status !== "queued") continue;
      freeSlots -= 1;
      startJob(job);
    }
  }, [startJob]);

  pumpRef.current = pump;

  const addJobs = useCallback(
    (staged: StagedFile[], target: UploadTarget = { mode: "new" }) => {
      const newJobs: UploadJob[] = staged.map(({ file, title }) => {
        jobIdCounter += 1;
        return {
          clientId: `upload-${jobIdCounter}`,
          file,
          title,
          target,
          status: "queued",
          progress: 0,
          version: null,
          errorMessage: null,
        };
      });
      jobsRef.current = [...jobsRef.current, ...newJobs];
      commit();
      pump();
    },
    [commit, pump],
  );

  /** Only meaningful for jobs still "queued" — in-flight uploads use cancelJob. */
  const removeJob = useCallback(
    (clientId: string) => {
      jobsRef.current = jobsRef.current.filter((j) => j.clientId !== clientId);
      commit();
    },
    [commit],
  );

  const cancelJob = useCallback(
    (clientId: string) => {
      abortsRef.current.get(clientId)?.();
      abortsRef.current.delete(clientId);
      jobsRef.current = jobsRef.current.filter((j) => j.clientId !== clientId);
      commit();
      pump();
    },
    [commit, pump],
  );

  return { jobs, addJobs, removeJob, cancelJob };
}
