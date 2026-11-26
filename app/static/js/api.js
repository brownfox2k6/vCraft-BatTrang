const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiClientError extends Error {
  constructor(message, { status = 0, code = "REQUEST_FAILED", meta = {} } = {}) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.meta = meta;
    this.fieldErrors = (meta && meta.field_errors) || {};
  }
}

function readCookie(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  const parts = document.cookie ? document.cookie.split(";") : [];
  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }
  return "";
}

export function getCsrfToken() {
  const cookieToken = readCookie("vcraft_csrf");
  if (cookieToken) {
    return cookieToken;
  }
  const meta = document.querySelector('meta[name="csrf-token"]');
  return (meta && meta.getAttribute("content")) || "";
}

export async function apiFetch(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});

  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  let body = options.body;
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && body !== null && !isFormData && typeof body !== "string") {
    body = JSON.stringify(body);
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }

  if (MUTATING_METHODS.has(method) && !headers.has("X-CSRF-Token")) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  }

  const response = await fetch(url, {
    ...options,
    method,
    headers,
    body,
    credentials: options.credentials || "same-origin",
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok || (payload && payload.error)) {
    const errorObj = (payload && payload.error) || {};
    const metaObj = (payload && payload.meta) || {};
    throw new ApiClientError(errorObj.message || "", {
      status: response.status,
      code: errorObj.code || "REQUEST_FAILED",
      meta: metaObj,
    });
  }

  return {
    data: payload ? payload.data : null,
    meta: (payload && payload.meta) || {},
    error: null,
    status: response.status,
  };
}
