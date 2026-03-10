/* ── state.js — single source of truth ──────────────────────────── */

const State = (() => {
  let _state = {
    currentJobId:  null,
    selectedFile:  null,
    chatHistory:   [],   // [{ role, content }]
    pollInterval:  null,
    speakerColors: {},   // name → css class index
    speakerIndex:  0,
  };

  return {
    get:    (key)        => _state[key],
    set:    (key, val)   => { _state[key] = val; },
    update: (patch)      => { Object.assign(_state, patch); },

    getSpeakerClass(name) {
      if (!(name in _state.speakerColors)) {
        _state.speakerColors[name] = _state.speakerIndex++ % 6;
      }
      return `spk-${_state.speakerColors[name]}`;
    },

    resetSpeakers() {
      _state.speakerColors = {};
      _state.speakerIndex  = 0;
    },

    pushChat(role, content) {
      _state.chatHistory.push({ role, content });
    },

    clearChat() {
      _state.chatHistory = [];
    },

    stopPoll() {
      if (_state.pollInterval) {
        clearInterval(_state.pollInterval);
        _state.pollInterval = null;
      }
    },
  };
})();
