/**
 * Client-side validation and fetch JSON submission for /dang-nhap and /dang-ky.
 */

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function setFormAlert(alertEl, message) {
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
  setFormAlert(alertEl, "");
  form.querySelectorAll("[data-field-error]").forEach((el) => {
    const fieldName = el.getAttribute("data-field-error");
    if (fieldName) {
      setFieldError(form, fieldName, "");
    }
  });
}

function validateLoginForm(form, data) {
  const errors = {};
  const email = (data.email || "").trim();
  const password = data.password || "";

  if (!EMAIL_PATTERN.test(email)) {
    errors.email = form.dataset.msgEmailInvalid || "";
  }
  if (!password) {
    errors.password = form.dataset.msgPasswordRequired || "";
  }
  return errors;
}

function validateRegisterForm(form, data) {
  const errors = {};
  const fullName = (data.full_name || "").trim().replace(/\s+/g, " ");
  const email = (data.email || "").trim();
  const password = data.password || "";
  const confirmPassword = data.confirm_password || "";

  if (fullName.length < 2 || fullName.length > 120) {
    errors.full_name = form.dataset.msgFullNameInvalid || "";
  }
  if (!EMAIL_PATTERN.test(email)) {
    errors.email = form.dataset.msgEmailInvalid || "";
  }
  if (password.length < 8) {
    errors.password = form.dataset.msgPasswordTooShort || "";
  } else if (password.length > 128) {
    errors.password = form.dataset.msgPasswordTooLong || "";
  } else if (!(/\p{L}/u.test(password) && /\p{Nd}/u.test(password))) {
    errors.password = form.dataset.msgPasswordWeak || "";
  }
  if (password !== confirmPassword) {
    errors.confirm_password = form.dataset.msgPasswordMismatch || "";
  }
  return errors;
}

function bindAuthForm(form) {
  const card = form.closest(".surface-card") || document;
  const alertEl = card.querySelector("[data-auth-alert]");
  const submitBtn = form.querySelector("[data-auth-submit]");
  const formType = form.getAttribute("data-auth-form");
  const endpoint = form.getAttribute("data-endpoint");
  if (!endpoint) {
    return;
  }

  // Defer to custom bilingual inline validation when JS is active while keeping HTML5 attributes as fallback.
  form.noValidate = true;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors(form, alertEl);

    const formData = new FormData(form);
    const values = Object.fromEntries(formData.entries());
    const clientErrors =
      formType === "register"
        ? validateRegisterForm(form, values)
        : validateLoginForm(form, values);

    const errorEntries = Object.entries(clientErrors);
    if (errorEntries.length > 0) {
      errorEntries.forEach(([field, msg]) => setFieldError(form, field, msg));
      setFormAlert(alertEl, form.dataset.msgValidation || "");
      const firstInvalid = form.querySelector('[aria-invalid="true"]');
      if (firstInvalid instanceof HTMLElement) {
        firstInvalid.focus();
      }
      return;
    }

    const payload =
      formType === "register"
        ? {
            full_name: String(values.full_name || ""),
            email: String(values.email || ""),
            password: String(values.password || ""),
            next: values.next ? String(values.next) : null,
          }
        : {
            email: String(values.email || ""),
            password: String(values.password || ""),
            next: values.next ? String(values.next) : null,
          };

    if (submitBtn) {
      submitBtn.disabled = true;
    }

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      const json = await response.json();

      if (!response.ok || json.error) {
        const fieldErrors = (json.meta && json.meta.field_errors) || {};
        Object.entries(fieldErrors).forEach(([field, msg]) => {
          setFieldError(form, field, String(msg));
        });
        const message = (json.error && json.error.message) || form.dataset.msgGeneric || "";
        setFormAlert(alertEl, message);
        return;
      }

      const target = (json.data && json.data.redirect_to) || "/";
      window.location.assign(target);
    } catch {
      setFormAlert(alertEl, form.dataset.msgGeneric || "");
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
      }
    }
  });
}

document.querySelectorAll("[data-auth-form]").forEach(bindAuthForm);
