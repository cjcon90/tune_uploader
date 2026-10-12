document.querySelectorAll("form[data-upload]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const bar = form.querySelector("progress");
    const status = form.querySelector(".progress");
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    bar.hidden = false;
    status.hidden = false;
    status.textContent = "Uploading…";
    const xhr = new XMLHttpRequest();
    xhr.open(form.method, form.action);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) bar.value = e.loaded / e.total;
    };
    xhr.upload.onload = () => {
      bar.removeAttribute("value");  // indeterminate bar while the server works
      button.setAttribute("aria-busy", "true");
      status.textContent = "Making your sheet music… this can take a minute.";
    };
    xhr.onload = () => {
      if (xhr.status < 400) { window.location = xhr.responseURL; return; }
      document.open(); document.write(xhr.responseText); document.close();
    };
    xhr.onerror = () => {
      status.textContent = "The connection dropped. Check your internet and try again.";
      button.disabled = false;
      button.removeAttribute("aria-busy");
      bar.hidden = true;
    };
    xhr.send(new FormData(form));
  });
});

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    await navigator.clipboard.writeText(button.dataset.copy);
    button.textContent = "Copied ✓";
  });
});
