/* Voice is a thin browser adapter over the same text-based knowledge engine. */
(() => {
  const byId = id => document.getElementById(id);
  const talk = byId('talk'), finish = byId('finish'), quiet = byId('quiet');
  const send = byId('send'), transcript = byId('transcript'), resident = byId('resident');
  const status = byId('status'), interim = byId('interim'), voiceSelect = byId('voice');
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const greeting = 'Hey WaterLine here, how can i help you?';
  let listening = false, busy = false, speaking = false, recognitionFailed = false, voiceActive = false;
  let finalText = '', pending = null, recognition = null, lastAnswer = '';
  let audio = null, audioUrl = null, speechAbort = null, cachedSpeech = null, preparingSpeech = false;
  let speechGeneration = 0, responseGeneration = 0, resumeTimer = null, discardSpeech = false;
  function setStatus(text, mode = 'idle') {
    status.textContent = text;
    document.body.dataset.mode = mode;
    byId('phase').textContent = {idle: 'Let’s talk.', listening: 'I’m listening.',
      thinking: 'One moment.', speaking: 'WaterLine is speaking.', error: 'Let’s try again.'}[mode];
  }
  function controls() {
    talk.disabled = !Recognition || listening || busy || speaking;
    talk.querySelector('span').textContent = listening ? 'Listening' : (busy || preparingSpeech) ? 'Thinking' : speaking ? 'Speaking' : voiceActive ? 'Continue' : 'Start conversation';
    finish.disabled = !listening;
    send.disabled = listening || busy;
    resident.disabled = busy || voiceActive;
    transcript.disabled = busy || listening;
    quiet.disabled = !speaking;
    byId('end-session').disabled = !voiceActive && !speaking && !busy && !listening;
    byId('replay').disabled = !lastAnswer || busy || listening;
    byId('control-hint').textContent = voiceActive ? 'Conversation active · listening pauses while I speak' : 'Speak naturally. Your assistant speaks back.';
  }
  function showComposer(show) {
    byId('composer').hidden = !show;
    byId('keyboard').setAttribute('aria-expanded', String(show));
  }
  function stopReply() {
    speechGeneration++;
    clearTimeout(resumeTimer);
    if (speechAbort) { speechAbort.abort(); speechAbort = null; }
    if (audio) { audio.onended = null; audio.onerror = null; audio.pause(); audio.removeAttribute('src'); audio.load(); audio = null; }
    if (audioUrl) { URL.revokeObjectURL(audioUrl); audioUrl = null; }
    speaking = false; preparingSpeech = false;
    controls();
  }
  function endConversation() {
    voiceActive = false; discardSpeech = true; responseGeneration++;
    clearTimeout(resumeTimer);
    if (recognition && listening) recognition.abort();
    listening = false;
    stopReply(); interim.textContent = '';
    setStatus('Conversation ended. Your reports are saved.');
    controls();
  }
  function resumeConversation() {
    if (!voiceActive || !byId('auto-send').checked) return;
    clearTimeout(resumeTimer);
    // Leave a short gap after output audio before enabling microphone capture again.
    resumeTimer = setTimeout(() => {
      if (voiceActive && !busy && !speaking && !listening) startListening();
    }, 450);
  }
  function message(who, text, result) {
    const card = document.createElement('article');
    card.className = 'message' + (who === 'You' ? ' resident' : '');
    const label = document.createElement('div');
    label.className = 'who'; label.textContent = who;
    const body = document.createElement('div'); body.className = 'message-body'; body.textContent = text;
    card.append(label, body);
    if (result) {
      const details = document.createElement('details');
      const summary = document.createElement('summary'); summary.textContent = 'View sources & saved reports';
      const data = document.createElement('pre');
      data.textContent = JSON.stringify({intent: result.intent, turn_id: result.turn_id,
        reports: result.reports, sources: result.sources}, null, 2);
      details.append(summary, data); card.append(details);
    }
    const conversation = byId('conversation');
    conversation.append(card); conversation.scrollTop = conversation.scrollHeight;
  }
  async function readReply(text, force = false, after = null) {
    if (!force && !byId('read-aloud').checked) { resumeConversation(); return; }
    stopReply();
    const spoken = text.replace(/[*`#]/g, '').replace(/\bcommunity report\s+[0-9a-f]{8}-[0-9a-f-]{27}\b/gi, 'a community report');
    const voice = voiceSelect.value, generation = speechGeneration;
    const controller = new AbortController(); speechAbort = controller;
    const timer = setTimeout(() => controller.abort(), 70000);
    speaking = true; preparingSpeech = true; controls();
    setStatus('Preparing your spoken reply…', 'thinking');
    try {
      let blob;
      if (cachedSpeech && cachedSpeech.text === spoken && cachedSpeech.voice === voice) {
        blob = cachedSpeech.blob;
      } else {
        const response = await fetch('/speech', {method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({text: spoken, voice}), signal: controller.signal});
        if (!response.ok) {
          const detail = await response.json().catch(() => ({}));
          throw new Error(typeof detail.detail === 'string' ? detail.detail : 'Speech generation is unavailable. Your text answer is below.');
        }
        blob = await response.blob();
        if (!blob.type.startsWith('audio/')) throw new Error('Spoken playback is unavailable. Your text answer is below.');
      }
      if (generation !== speechGeneration) return;
      cachedSpeech = {text: spoken, voice, blob};
      audioUrl = URL.createObjectURL(blob); audio = new Audio(audioUrl);
      audio.onended = () => {
        if (generation !== speechGeneration) return;
        stopReply(); setStatus('Your turn.');
        if (after) after(); else resumeConversation();
      };
      audio.onerror = () => {
        if (generation !== speechGeneration) return;
        stopReply(); voiceActive = false; controls();
        setStatus('Playback was unavailable. Try “Hear last reply”. Your text answer is below.', 'error');
      };
      await audio.play();
      if (generation !== speechGeneration) return;
      preparingSpeech = false; controls(); setStatus('You can interrupt at any time.', 'speaking');
    } catch (error) {
      if (generation !== speechGeneration) return;
      stopReply(); voiceActive = false; controls();
      setStatus(error.name === 'NotAllowedError' ? 'Your browser blocked audio. Click “Hear last reply” to play it.' :
        (error.name === 'AbortError' ? 'Speech generation timed out. Try “Hear last reply”.' : error.message), 'error');
    } finally {
      clearTimeout(timer);
      if (speechAbort === controller) speechAbort = null;
    }
  }
  async function submit() {
    if (busy || listening) return;
    const text = transcript.value.trim(), user = resident.value;
    if (!text) { setStatus('Say or type a message first.'); return; }
    if (text.length > 5000) { setStatus('Please shorten your message to 5,000 characters.'); return; }
    stopReply(); busy = true; controls();
    const generation = responseGeneration;
    if (!pending || pending.text !== text || pending.user !== user) {
      pending = {text, user, id: crypto.randomUUID()}; message('You', text);
    }
    setStatus('Let me check…', 'thinking');
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 180000);
    try {
      const response = await fetch('/interact', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: pending.text, user_id: pending.user, turn_id: pending.id}),
        signal: controller.signal
      });
      if (!response.ok) throw new Error('Agent unavailable');
      const result = await response.json();
      if (typeof result.answer !== 'string') throw new Error('Invalid agent answer');
      message('WaterLine', result.answer, result);
      lastAnswer = result.answer; pending = null; transcript.value = '';
      setStatus('Your turn.');
      if (generation === responseGeneration) readReply(result.answer);
      else setStatus('Reply received. Conversation ended.');
    } catch {
      voiceActive = false; showComposer(true);
      setStatus('Could not get an answer. Your report may already be saved. Send the message again to retry the same turn.', 'error');
    } finally {
      clearTimeout(timer); busy = false; controls();
    }
  }
  function startListening() {
    if (!recognition || busy || listening || speaking) return;
    clearTimeout(resumeTimer);
    finalText = ''; recognitionFailed = false; discardSpeech = false;
    interim.textContent = ''; listening = true; controls();
    setStatus('Say the water point and village. Pause when you’re done.', 'listening');
    try { recognition.start(); }
    catch {
      listening = false; voiceActive = false; controls();
      setStatus('Could not start the microphone. Try again or type your message.', 'error');
    }
  }
  if (Recognition) {
    recognition = new Recognition();
    recognition.lang = 'en-US'; recognition.interimResults = true; recognition.continuous = false;
    recognition.onresult = event => {
      if (discardSpeech || !listening) return;
      const results = Array.from(event.results);
      finalText = results.filter(r => r.isFinal).map(r => r[0].transcript).join(' ').trim();
      transcript.value = finalText;
      interim.textContent = results.map(r => r[0].transcript).join(' ');
    };
    recognition.onerror = event => {
      if (discardSpeech) return;
      recognitionFailed = true; voiceActive = false;
      const messages = {
        'not-allowed': 'Microphone access was denied. Allow it in browser settings, then try again.',
        'audio-capture': 'No microphone is available. Connect one or type your message.',
        'no-speech': 'No speech detected. Tap the microphone to try again.',
        'network': 'Speech recognition could not connect. Try again or type your message.'
      };
      setStatus(messages[event.error] || 'Recognition stopped. Review the transcript or try again.', 'error');
    };
    recognition.onend = () => {
      listening = false; interim.textContent = ''; controls();
      if (recognitionFailed || discardSpeech) return;
      if (!finalText) { voiceActive = false; controls(); setStatus('No speech detected. Tap the microphone to try again.'); return; }
      if (byId('auto-send').checked) void submit();
      else { showComposer(true); setStatus('Check the water point and village, then send your message.'); }
    };
    talk.onclick = () => {
      const starting = !voiceActive;
      voiceActive = true;
      if (starting) {
        message('WaterLine', greeting);
        lastAnswer = greeting;
        if (byId('read-aloud').checked) void readReply(greeting, false, startListening);
        else startListening();
      } else startListening();
    };
    finish.onclick = () => { if (listening) recognition.stop(); };
  } else {
    byId('support').textContent = 'Speech recognition is unavailable in this browser. Try Chrome with microphone access, or type below. Spoken replies may still be available.';
    showComposer(true);
  }
  byId('keyboard').onclick = () => {
    const show = byId('composer').hidden;
    if (show && (voiceActive || speaking)) endConversation();
    showComposer(show); if (show) transcript.focus();
  };
  byId('read-aloud').onchange = () => { if (!byId('read-aloud').checked) { stopReply(); setStatus('Spoken replies paused.'); } };
  byId('end-session').onclick = endConversation;
  byId('replay').onclick = () => { if (lastAnswer && !listening && !busy) readReply(lastAnswer, true); };
  quiet.onclick = () => { stopReply(); setStatus('Reply interrupted. Your turn.'); resumeConversation(); };
  send.onclick = () => { void submit(); };
  window.addEventListener('pagehide', endConversation);
  controls();
})();
