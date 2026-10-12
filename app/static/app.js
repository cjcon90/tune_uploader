const PLAY = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4v16l13-8z"/></svg>';
const PAUSE = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>';
const MAX_BYTES = 200 * 1024 * 1024;  // matches MAX_UPLOAD_BYTES in app/config.py

const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
const megabytes = (bytes) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;

// One tune plays at a time, and every play button follows its own audio.
function wirePlayButton(button, audio) {
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    document.querySelectorAll("audio").forEach((other) => { if (other !== audio) other.pause(); });
    if (audio.paused) audio.play(); else audio.pause();
  });
  audio.addEventListener("play", () => { button.innerHTML = PAUSE; button.setAttribute("aria-label", "Pause"); });
  audio.addEventListener("pause", () => { button.innerHTML = PLAY; button.setAttribute("aria-label", "Play"); });
}

document.querySelectorAll("[data-play]").forEach((button) => wirePlayButton(button, button.nextElementSibling));

document.querySelectorAll("[data-player]").forEach((player) => {
  const audio = player.querySelector("audio");
  const fill = player.querySelector(".track i");
  const time = player.querySelector(".time");
  wirePlayButton(player.querySelector("button"), audio);
  const update = () => {
    if (!audio.duration) return;
    fill.style.width = `${(audio.currentTime / audio.duration) * 100}%`;
    time.textContent = `${clock(audio.currentTime)} / ${clock(audio.duration)}`;
  };
  audio.addEventListener("loadedmetadata", update);
  audio.addEventListener("timeupdate", update);
});

document.querySelectorAll("[data-href]").forEach((row) => {
  row.addEventListener("click", () => { window.location = row.dataset.href; });
});

document.querySelectorAll("[data-filter]").forEach((input) => {
  const rows = [...document.querySelectorAll("[data-title]")];
  const empty = document.querySelector("[data-empty]");
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    rows.forEach((row) => { row.hidden = !row.dataset.title.includes(q); });
    empty.hidden = rows.some((row) => !row.hidden) || rows.length === 0;
  });
});

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    await navigator.clipboard.writeText(button.dataset.copy);
    button.textContent = "Copied ✓";
  });
});

document.querySelectorAll(".pick input").forEach((input) => {
  const pick = input.closest(".pick");
  const name = pick.querySelector("[data-file-name]");
  const size = pick.querySelector("[data-file-size]");
  const prompt = name.textContent;
  input.addEventListener("change", () => {
    const file = input.files[0];
    pick.classList.toggle("chosen", Boolean(file));
    name.textContent = file ? file.name : prompt;
    size.textContent = file ? `${megabytes(file.size)} ✓` : "";
  });
});

document.querySelectorAll("form[data-confirm]").forEach((form) => {
  const scrim = form.querySelector(".scrim");
  const sheet = form.querySelector(".sheet");
  const show = (open) => { scrim.hidden = !open; sheet.hidden = !open; };
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    show(true);
    sheet.querySelector("[data-no]").focus();
  });
  sheet.querySelector("[data-yes]").addEventListener("click", () => form.submit());
  sheet.querySelector("[data-no]").addEventListener("click", () => show(false));
  scrim.addEventListener("click", () => show(false));
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") show(false); });
});

document.querySelectorAll("form[data-upload]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const prog = form.querySelector(".prog");
    const fill = prog.querySelector("i");
    const status = prog.querySelector("span");
    const button = form.querySelector("button[type=submit]");
    const files = [...form.querySelectorAll("input[type=file]")].flatMap((input) => [...input.files]);
    const bytes = files.reduce((total, file) => total + file.size, 0);
    prog.hidden = false;
    if (bytes > MAX_BYTES) {
      status.textContent = "That file is too big. Recordings and sheet music must be under 200 MB.";
      return;
    }
    button.disabled = true;
    status.textContent = files.length ? "Uploading… 0%" : "Saving…";
    const xhr = new XMLHttpRequest();
    xhr.open(form.method, form.action);
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const pct = Math.round((e.loaded / e.total) * 100);
      fill.style.width = `${pct}%`;
      if (files.length) status.textContent = `Uploading… ${pct}%`;
    };
    xhr.upload.onload = () => {
      prog.classList.add("indeterminate");
      button.setAttribute("aria-busy", "true");
      status.textContent = "Making your sheet music… this can take a minute.";
    };
    xhr.onload = () => {
      if (xhr.status < 400) { window.location = xhr.responseURL; return; }
      document.open(); document.write(xhr.responseText); document.close();
    };
    xhr.onerror = () => {
      status.textContent = "The connection dropped. Check your internet and try again.";
      prog.classList.remove("indeterminate");
      button.disabled = false;
      button.removeAttribute("aria-busy");
    };
    xhr.send(new FormData(form));
  });
});

document.querySelectorAll(".toast").forEach((toast) => setTimeout(() => toast.remove(), 3500));
