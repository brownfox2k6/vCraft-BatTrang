/**
 * Reusable multi-image uploader module with drag-and-drop preview, queue removal,
 * and CSRF-protected FormData upload via apiFetch.
 */

import { ApiClientError, apiFetch } from "./api.js";

const DEFAULT_MAX_FILES = 10;
const DEFAULT_MAX_BYTES = 10 * 1024 * 1024;
const ALLOWED_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export class MediaUploader {
  constructor(root) {
    this.root = root;
    this.endpoint = root.dataset.endpoint || "/api/media/upload";
    this.category = root.dataset.category || "general";
    this.maxFiles = Number(root.dataset.maxFiles) || DEFAULT_MAX_FILES;
    this.maxBytes = Number(root.dataset.maxBytes) || DEFAULT_MAX_BYTES;
    this.input = root.querySelector("[data-media-input]");
    this.dropzone = root.querySelector("[data-media-dropzone]");
    this.previewList = root.querySelector("[data-media-previews]");
    this.uploadBtn = root.querySelector("[data-media-upload]");
    this.statusEl = root.querySelector("[data-media-status]");
    this.errorEl = root.querySelector("[data-media-error]");
    this.hiddenIdsInput = root.querySelector("[data-media-ids]");

    /** @type {Array<{id: string, file: File, objectUrl: string}>} */
    this.queue = [];
    /** @type {Array<object>} */
    this.uploadedAssets = [];

    this._bindEvents();
  }

  _bindEvents() {
    if (this.input instanceof HTMLInputElement) {
      this.input.addEventListener("change", () => {
        if (this.input.files && this.input.files.length > 0) {
          this.addFiles(this.input.files);
          this.input.value = "";
        }
      });
    }

    if (this.dropzone instanceof HTMLElement) {
      this.dropzone.addEventListener("dragover", (event) => {
        event.preventDefault();
        this.dropzone.classList.add("border-cobalt", "bg-cobalt-soft");
      });
      this.dropzone.addEventListener("dragleave", () => {
        this.dropzone.classList.remove("border-cobalt", "bg-cobalt-soft");
      });
      this.dropzone.addEventListener("drop", (event) => {
        event.preventDefault();
        this.dropzone.classList.remove("border-cobalt", "bg-cobalt-soft");
        if (event.dataTransfer && event.dataTransfer.files.length > 0) {
          this.addFiles(event.dataTransfer.files);
        }
      });
    }

    if (this.uploadBtn instanceof HTMLButtonElement) {
      this.uploadBtn.addEventListener("click", () => {
        void this.upload();
      });
    }
  }

  _setError(message) {
    if (!this.errorEl) {
      return;
    }
    this.errorEl.textContent = message || "";
    this.errorEl.hidden = !message;
  }

  _setStatus(message) {
    if (!this.statusEl) {
      return;
    }
    this.statusEl.textContent = message || "";
    this.statusEl.hidden = !message;
  }

  addFiles(fileList) {
    this._setError("");
    const incoming = Array.from(fileList);
    if (this.uploadedAssets.length + this.queue.length + incoming.length > this.maxFiles) {
      this._setError(this.root.dataset.msgTooMany || "Too many files selected.");
      return;
    }

    for (const file of incoming) {
      if (file.type && !ALLOWED_MIME_TYPES.has(file.type)) {
        this._setError(
          this.root.dataset.msgInvalidFormat || "Only JPEG, PNG, or WebP images are supported.",
        );
        continue;
      }
      if (file.size > this.maxBytes) {
        this._setError(this.root.dataset.msgTooLarge || "Image exceeds maximum allowed size.");
        continue;
      }
      const objectUrl = URL.createObjectURL(file);
      this.queue.push({
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        file,
        objectUrl,
      });
    }

    this._renderPreviews();
  }

  removeQueuedFile(entryId) {
    const idx = this.queue.findIndex((item) => item.id === entryId);
    if (idx === -1) {
      return;
    }
    const [removed] = this.queue.splice(idx, 1);
    URL.revokeObjectURL(removed.objectUrl);
    this._renderPreviews();
  }

  clearQueue() {
    for (const item of this.queue) {
      URL.revokeObjectURL(item.objectUrl);
    }
    this.queue = [];
    this._renderPreviews();
  }

  _renderPreviews() {
    if (!this.previewList) {
      return;
    }
    this.previewList.innerHTML = "";
    const removeAria = this.root.dataset.msgRemoveAria || "Remove image";

    for (const entry of this.queue) {
      const card = document.createElement("div");
      card.className = "relative overflow-hidden rounded-lg border border-clay-border bg-surface p-2";

      const img = document.createElement("img");
      img.src = entry.objectUrl;
      img.alt = entry.file.name;
      img.className = "w-full rounded-md";

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.textContent = "×";
      removeBtn.setAttribute("aria-label", removeAria);
      removeBtn.className =
        "absolute top-3 right-3 inline-flex h-8 w-8 items-center justify-center rounded-full bg-cobalt-action text-xs font-semibold text-on-cobalt hover:bg-cobalt-action-hover";
      removeBtn.addEventListener("click", () => this.removeQueuedFile(entry.id));

      card.append(img, removeBtn);
      this.previewList.append(card);
    }

    if (this.uploadBtn instanceof HTMLButtonElement) {
      this.uploadBtn.disabled = this.queue.length === 0;
    }
  }

  async upload() {
    this._setError("");
    if (this.queue.length === 0) {
      this._setError(this.root.dataset.msgNoFiles || "Please select at least one image.");
      return [];
    }

    const formData = new FormData();
    formData.append("category", this.category);
    for (const entry of this.queue) {
      formData.append("files", entry.file, entry.file.name);
    }

    if (this.uploadBtn instanceof HTMLButtonElement) {
      this.uploadBtn.disabled = true;
    }
    this._setStatus(this.root.dataset.msgUploading || "Uploading...");

    try {
      const result = await apiFetch(this.endpoint, {
        method: "POST",
        body: formData,
      });
      const assets = Array.isArray(result.data) ? result.data : [];
      this.uploadedAssets.push(...assets);
      if (this.hiddenIdsInput instanceof HTMLInputElement) {
        this.hiddenIdsInput.value = this.uploadedAssets.map((a) => a.id).join(",");
      }
      this.clearQueue();
      this._setStatus("");
      this.root.dispatchEvent(
        new CustomEvent("media:uploaded", {
          bubbles: true,
          detail: {
            assets,
            assetIds: assets.map((a) => a.id),
          },
        }),
      );
      return assets;
    } catch (error) {
      this._setStatus("");
      if (error instanceof ApiClientError && error.message) {
        this._setError(error.message);
      } else {
        this._setError(this.root.dataset.msgUploadFailed || "Upload failed. Please try again.");
      }
      return [];
    } finally {
      if (this.uploadBtn instanceof HTMLButtonElement) {
        this.uploadBtn.disabled = this.queue.length === 0;
      }
    }
  }
}

export function initMediaUploaders(scope = document) {
  const instances = [];
  scope.querySelectorAll("[data-media-uploader]").forEach((el) => {
    if (el instanceof HTMLElement) {
      instances.push(new MediaUploader(el));
    }
  });
  return instances;
}

initMediaUploaders();
