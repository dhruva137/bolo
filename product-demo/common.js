"use strict";

const iconPaths = {
  play: '<path d="m8 5 11 7-11 7Z" fill="currentColor" stroke="none"/>',
  pause: '<path d="M8 5v14m8-14v14" stroke-width="3.5"/>'
};

function icon(name) {
  return '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (iconPaths[name] || "") + "</svg>";
}

document.querySelectorAll("[data-icon]").forEach(el => el.innerHTML = icon(el.dataset.icon));
const wave = document.querySelector(".wave");
if (wave) {
  for (const height of [5, 8, 4, 12, 17, 9, 6, 14, 17, 7, 5, 10, 16, 18, 9, 5, 7, 13, 15, 8, 4, 8, 11, 6, 9, 4]) {
    const bar = document.createElement("b");
    bar.style.height = height + "px";
    wave.append(bar);
  }
  const audio = document.getElementById("sample");
  const toggle = document.getElementById("sample-play");
  function audioState() {
    toggle.innerHTML = icon(audio.paused ? "play" : "pause");
    toggle.setAttribute("aria-label", audio.paused ? "Play example voice note" : "Pause example voice note");
  }
  toggle.onclick = async () => {
    if (!audio.paused) return audio.pause();
    try {
      await audio.play();
    } catch {
      document.querySelector(".audio-label").textContent = "Audio unavailable · example transcript";
    }
  };
  audio.onplay = audio.onpause = audio.onended = audioState;
}
