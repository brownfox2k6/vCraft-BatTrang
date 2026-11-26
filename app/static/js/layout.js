/**
 * Accessible drawer controller shared by the public mobile header and workspace sidebar.
 */

function setDrawerState(drawerName, open) {
  const drawer = document.querySelector(`[data-drawer="${drawerName}"]`);
  const backdrop = document.querySelector(`[data-drawer-backdrop="${drawerName}"]`);
  const toggles = document.querySelectorAll(`[data-drawer-toggle="${drawerName}"]`);

  if (!drawer) {
    return;
  }

  drawer.hidden = !open;
  if (backdrop) {
    backdrop.hidden = !open;
  }
  toggles.forEach((button) => {
    button.setAttribute("aria-expanded", String(open));
  });
}

function initDrawers() {
  const toggles = document.querySelectorAll("[data-drawer-toggle]");
  toggles.forEach((button) => {
    button.addEventListener("click", () => {
      const name = button.getAttribute("data-drawer-toggle");
      if (!name) {
        return;
      }
      const isExpanded = button.getAttribute("aria-expanded") === "true";
      setDrawerState(name, !isExpanded);
    });
  });

  const closers = document.querySelectorAll("[data-drawer-close]");
  closers.forEach((closer) => {
    closer.addEventListener("click", () => {
      const name = closer.getAttribute("data-drawer-close");
      if (name) {
        setDrawerState(name, false);
      }
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    document.querySelectorAll("[data-drawer]:not([hidden])").forEach((drawer) => {
      const name = drawer.getAttribute("data-drawer");
      if (name) {
        setDrawerState(name, false);
      }
    });
  });
}

function initLogoutForms() {
  document.querySelectorAll("[data-logout-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const nextInput = form.querySelector('input[name="next"]');
      const nextValue =
        nextInput instanceof HTMLInputElement &&
        nextInput.value.startsWith("/") &&
        !nextInput.value.startsWith("//")
          ? nextInput.value
          : "/";
      try {
        const response = await fetch("/api/auth/logout", {
          method: "POST",
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (response.ok) {
          window.location.assign(nextValue);
          return;
        }
      } catch {
        // Fall through to standard form submission if fetch fails.
      }
      form.submit();
    });
  });
}

initDrawers();
initLogoutForms();
