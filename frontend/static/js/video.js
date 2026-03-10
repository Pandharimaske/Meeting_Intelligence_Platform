/* ── video.js — video player control ────────────────────────────── */

const Video = (() => {

  let _player = null;

  function init() {
    _player = document.getElementById('videoPlayer');
  }

  function load(src) {
    const wrapper   = document.getElementById('videoWrapper');
    const noSrcDiv  = document.getElementById('videoNoSrc');

    if (!src) {
      _player.classList.add('hidden');
      noSrcDiv.classList.remove('hidden');
      return;
    }

    _player.classList.remove('hidden');
    noSrcDiv.classList.add('hidden');
    _player.src = src;
    _player.load();
  }

  /* Seek to a HH:MM:SS or MM:SS timestamp string */
  function seekTo(ts) {
    if (!_player) return;
    const parts  = ts.split(':').map(Number);
    const secs   = parts.length === 3
      ? parts[0] * 3600 + parts[1] * 60 + parts[2]
      : parts[0] * 60 + parts[1];
    _player.currentTime = secs;
    _player.play().catch(() => {});

    /* Brief flash on the player to draw the user's eye */
    document.getElementById('videoWrapper').style.boxShadow = '0 0 0 2px var(--accent)';
    setTimeout(() => document.getElementById('videoWrapper').style.boxShadow = '', 800);
  }

  return { init, load, seekTo };
})();
