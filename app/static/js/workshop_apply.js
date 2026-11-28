/**
 * Two-layer validated household workshop registration form handler (/dang-ky-xuong).
 * Uses apiFetch (auto X-CSRF-Token) and renders the APP-xxx confirmation card in-place.
 */

import { ApiClientError, apiFetch } from "./api.js";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_PATTERN = /^[0-9+\-\s().]{8,32}$/;

function setAlert(alertEl, message) {
  if (!alertEl) {
    return;
  }
  alertEl.textContent = message || "";
  alertEl.hidden = !message;
}

function setFieldError(form, fieldName, message) {
  const input = form.querySelector(`[name="${fieldName}"]`);
  const errorEl = form.querySelector(`[data-field-error="${fieldName}"]`);
  if (input) {
    input.setAttribute("aria-invalid", message ? "true" : "false");
    input.classList.toggle("form-input-error", Boolean(message));
  }
  if (errorEl) {
    errorEl.textContent = message || "";
    errorEl.hidden = !message;
  }
}

function clearErrors(form, alertEl) {
  setAlert(alertEl, "");
  form.querySelectorAll("[data-field-error]").forEach((el) => {
    const fieldName = el.getAttribute("data-field-error");
    if (fieldName) {
      setFieldError(form, fieldName, "");
    }
  });
}

function parseMediaIds(raw) {
  return String(raw || "")
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

function validateForm(form, values) {
  const errors = {};
  const artisanName = String(values.artisan_name || "").trim().replace(/\s+/g, " ");
  const email = String(values.email || "").trim();
  const phone = String(values.phone || "").trim();
  const digits = phone.replace(/\D/g, "");
  const password = String(values.password || "");
  const confirmPassword = String(values.confirm_password || "");
  const nameVi = String(values.name_vi || "").trim();
  const addressVi = String(values.address_vi || "").trim();
  const historyVi = String(values.history_vi || "").trim();
  const openingHours = String(values.opening_hours || "").trim();
  const latRaw = String(values.latitude || "").trim();
  const lngRaw = String(values.longitude || "").trim();

  if (artisanName.length < 2 || artisanName.length > 120) {
    errors.artisan_name = form.dataset.msgArtisanName || "";
  }
  if (!EMAIL_PATTERN.test(email)) {
    errors.email = form.dataset.msgEmailInvalid || "";
  }
  if (!PHONE_PATTERN.test(phone) || digits.length < 8 || digits.length > 15) {
    errors.phone = form.dataset.msgPhoneInvalid || "";
  }
  if (password.length < 8) {
    errors.password = form.dataset.msgPasswordShort || "";
  } else if (password.length > 128) {
    errors.password = form.dataset.msgPasswordLong || "";
  } else if (!(/\p{L}/u.test(password) && /\p{Nd}/u.test(password))) {
    errors.password = form.dataset.msgPasswordWeak || "";
  }
  if (password !== confirmPassword) {
    errors.confirm_password = form.dataset.msgPasswordMismatch || "";
  }
  if (nameVi.length < 2 || nameVi.length > 160) {
    errors.name_vi = form.dataset.msgNameVi || "";
  }
  if (addressVi.length < 5 || addressVi.length > 255) {
    errors.address_vi = form.dataset.msgAddressVi || "";
  }
  if (historyVi.length < 10) {
    errors.history_vi = form.dataset.msgHistoryVi || "";
  }
  if (openingHours.length < 3 || openingHours.length > 80) {
    errors.opening_hours = form.dataset.msgOpeningHours || "";
  }
  if (latRaw || lngRaw) {
    const lat = Number(latRaw);
    const lng = Number(lngRaw);
    if (!latRaw || !lngRaw) {
      errors.latitude = form.dataset.msgCoordsPair || "";
      errors.longitude = form.dataset.msgCoordsPair || "";
    } else {
      if (Number.isNaN(lat) || lat < -90 || lat > 90) {
        errors.latitude = form.dataset.msgLatitude || "";
      }
      if (Number.isNaN(lng) || lng < -180 || lng > 180) {
        errors.longitude = form.dataset.msgLongitude || "";
      }
    }
  }
  if (parseMediaIds(values.workshop_media_ids).length === 0) {
    errors.workshop_media_ids = form.dataset.msgWorkshopMedia || "";
  }
  if (parseMediaIds(values.certificate_media_ids).length === 0) {
    errors.certificate_media_ids = form.dataset.msgCertificateMedia || "";
  }
  return errors;
}

function initUploadedPreviews(form) {
  form.addEventListener("media:uploaded", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const group = target.dataset.uploaderGroup;
    const listEl = group ? form.querySelector(`[data-uploaded-list="${group}"]`) : null;
    const detail = event instanceof CustomEvent ? event.detail : null;
    const assets = detail && Array.isArray(detail.assets) ? detail.assets : [];

    if (group === "workshop") {
      setFieldError(form, "workshop_media_ids", "");
    } else if (group === "certificate") {
      setFieldError(form, "certificate_media_ids", "");
    }

    if (!listEl) {
      return;
    }
    for (const asset of assets) {
      const card = document.createElement("div");
      card.className = "overflow-hidden rounded-lg border border-clay-border bg-surface p-2";
      const img = document.createElement("img");
      img.src = asset.thumb_url;
      img.alt = group || "uploaded";
      img.loading = "lazy";
      img.decoding = "async";
      img.className = "w-full rounded-md";
      card.append(img);
      listEl.append(card);
    }
  });
}

function initWorkshopApplyForm(form) {
  const card = form.closest(".surface-card") || document;
  const alertEl = card.querySelector("[data-apply-alert]");
  const successEl = card.querySelector("[data-apply-success]");
  const submitBtn = form.querySelector("[data-apply-submit]");
  const endpoint = form.dataset.endpoint || "/api/workshop-applications";

  form.noValidate = true;
  initUploadedPreviews(form);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors(form, alertEl);

    const formData = new FormData(form);
    const values = Object.fromEntries(formData.entries());
    const clientErrors = validateForm(form, values);
    const entries = Object.entries(clientErrors);

    if (entries.length > 0) {
      entries.forEach(([field, msg]) => setFieldError(form, field, msg));
      setAlert(alertEl, form.dataset.msgValidation || "");
      const firstInvalid = form.querySelector('[aria-invalid="true"]:not([type="hidden"])');
      if (firstInvalid instanceof HTMLElement) {
        firstInvalid.focus();
      }
      return;
    }

    const latRaw = String(values.latitude || "").trim();
    const lngRaw = String(values.longitude || "").trim();
    const payload = {
      artisan_name: String(values.artisan_name || ""),
      email: String(values.email || ""),
      phone: String(values.phone || ""),
      password: String(values.password || ""),
      name_vi: String(values.name_vi || ""),
      name_en: String(values.name_en || "") || null,
      tagline_vi: String(values.tagline_vi || "") || null,
      tagline_en: String(values.tagline_en || "") || null,
      address_vi: String(values.address_vi || ""),
      address_en: String(values.address_en || "") || null,
      history_vi: String(values.history_vi || ""),
      history_en: String(values.history_en || "") || null,
      opening_hours: String(values.opening_hours || ""),
      is_open_now: form.querySelector('[name="is_open_now"]')?.checked ?? true,
      has_experience: form.querySelector('[name="has_experience"]')?.checked ?? false,
      experience_desc_vi: String(values.experience_desc_vi || "") || null,
      experience_desc_en: String(values.experience_desc_en || "") || null,
      latitude: latRaw ? Number(latRaw) : null,
      longitude: lngRaw ? Number(lngRaw) : null,
      workshop_media_ids: parseMediaIds(values.workshop_media_ids),
      certificate_media_ids: parseMediaIds(values.certificate_media_ids),
    };

    if (submitBtn instanceof HTMLButtonElement) {
      submitBtn.disabled = true;
      submitBtn.textContent = form.dataset.msgSubmitting || submitBtn.textContent;
    }

    try {
      const result = await apiFetch(endpoint, {
        method: "POST",
        body: payload,
      });
      const data = result.data || {};
      if (successEl) {
        const codeEl = successEl.querySelector("[data-success-code]");
        const slugEl = successEl.querySelector("[data-success-slug]");
        const msgEl = successEl.querySelector("[data-success-message]");
        if (codeEl) codeEl.textContent = data.application_code || "";
        if (slugEl) slugEl.textContent = data.proposed_slug ? `/xuong/${data.proposed_slug}` : "";
        if (msgEl && data.message) msgEl.textContent = data.message;
        successEl.hidden = false;
      }
      form.hidden = true;
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (error) {
      if (error instanceof ApiClientError) {
        Object.entries(error.fieldErrors).forEach(([field, msg]) => {
          setFieldError(form, field, String(msg));
        });
        setAlert(alertEl, error.message || form.dataset.msgGeneric || "");
      } else {
        setAlert(alertEl, form.dataset.msgGeneric || "");
      }
    } finally {
      if (submitBtn instanceof HTMLButtonElement) {
        submitBtn.disabled = false;
        submitBtn.textContent = form.dataset.msgSubmit || submitBtn.textContent;
      }
    }
  });
}

document.querySelectorAll("[data-workshop-apply-form]").forEach(initWorkshopApplyForm);
