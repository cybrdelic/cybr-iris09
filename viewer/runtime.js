(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const source = JSON.parse($('shaderSource').textContent);
  const shareSource = JSON.parse($('shareSource').textContent) || source;
  const canvas = $('scene');
  const poster = $('poster');
  const film = $('film');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const controls = {play:$('play'),seek:$('seek'),quality:$('quality'),samples:$('samples'),reset:$('reset')};
  const duration = 10;
  const state = {
    time:0, frame:0, playing:!reducedMotion, mode:film ? 'film' : 'live',
    dirty:true, lost:false, seeking:false, pointer:null, lastPointer:[0,0],
    mouse:[0,0,-1,-1], drag:[0,0], scroll:0,
    previousTime:0, measuredFrames:0, measuredStart:0, fps:0
  };
  let gl = null, program = null, toastTimer = 0, animationStarted = false;
  let worker = null, busy = false, deadline = null, renderedTime = null;
  let allowExperimentalLive = false;
  const display = canvas.getContext('2d', {alpha:false});
  window.irisDiagnostics = {phase:'film',frames:0,renderer:null,lastError:null};
  const liveNotice = document.createElement('p');
  liveNotice.id = 'liveNotice'; liveNotice.setAttribute('role','status');
  liveNotice.style.cssText = 'max-width:38ch;font-size:11px;line-height:1.5;letter-spacing:normal;color:#e4c6a8;pointer-events:auto';
  $('modeSwitch').insertAdjacentElement('afterend',liveNotice);
  function stopWorker() {
    clearTimeout(deadline); deadline = null;
    if (worker) worker.terminate(); worker = null; busy = false; gl = null; program = null;
  }
  function armDeadline(phase, milliseconds) {
    clearTimeout(deadline);
    deadline = setTimeout(() => {
      const message = `${phase} exceeded ${milliseconds/1000}s. Live stopped; Film and shader downloads remain available.`;
      window.irisDiagnostics.lastError = message;
      liveNotice.textContent = message;
      stopWorker(); fail('Live time limit', new Error(message));
    }, milliseconds);
  }

  const vertexSource = `#version 300 es
  precision highp float;
  void main(){
    vec2 p=vec2(float((gl_VertexID<<1)&2),float(gl_VertexID&2));
    gl_Position=vec4(p*2.0-1.0,0.0,1.0);
  }`;

  function fragmentSource() {
    const body = source
      .replace(/^[ \t]*#version[^\n]*$/gm,'')
      .replace(/^[ \t]*precision\s+(?:lowp|mediump|highp)\s+\w+\s*;/gm,'')
      .replace(/^[ \t]*#define[ \t]+AA\b[^\n]*$/gm,'');
    return `#version 300 es
precision highp float;
precision highp int;
#define AA ${Number(controls.samples.value)}
uniform vec2 u_resolution;
uniform float u_time;
uniform float u_time_delta;
uniform int u_frame;
uniform vec4 u_mouse;
uniform vec2 u_drag;
uniform float u_scroll;
out vec4 fragColor;
#line 1
${body}`;
  }

  function fail(title, error) {
    $('errorTitle').textContent = title;
    $('errorText').textContent = String(error && error.message || error);
    state.playing = false;
    if (film) {
      $('error').hidden = true;
      console.warn(title, error);
      setMode('film', 'Live view is unavailable here. Showing the rendered film.');
      return;
    }
    $('error').hidden = false;
    if (state.lost || !gl || !program) showPoster();
    updatePlay();
    $('status').textContent = state.lost ? 'Context lost' : 'Render error';
  }

  function showPoster() {
    canvas.classList.remove('ready');
    if (poster) poster.classList.remove('rendered');
  }

  function showRenderedFrame() {
    if (state.mode !== 'live') return;
    canvas.classList.add('ready');
    if (poster) poster.classList.add('rendered');
  }

  function toast(text, milliseconds=3000) {
    clearTimeout(toastTimer);
    $('toast').textContent = text;
    $('toast').classList.add('visible');
    toastTimer = setTimeout(() => $('toast').classList.remove('visible'),milliseconds);
  }

  function updateFilmReadout() {
    if (!film || state.mode !== 'film') return;
    $('status').textContent = film.paused ? 'Film · Paused' : 'Rendered film · Loop';
    $('resolution').textContent = film.videoWidth
      ? `${film.videoWidth} × ${film.videoHeight} · MP4`
      : 'Embedded MP4';
  }

  function playFilm() {
    if (!film) return;
    const pending = film.play();
    if (pending && typeof pending.catch === 'function') {
      pending.catch(() => {
        if (state.mode === 'film') {
          updateFilmReadout();
          toast('Use the video play button to start the film.');
        }
      });
    }
  }

  function setMode(mode, message='') {
    if (mode === 'film' && !film) mode = 'live';
    state.mode = mode;
    document.body.dataset.mode = mode;
    $('filmMode').setAttribute('aria-pressed',String(mode === 'film'));
    $('liveMode').setAttribute('aria-pressed',String(mode === 'live'));
    state.previousTime = 0; state.measuredStart = 0; state.measuredFrames = 0;
    $('error').hidden = true;
    if (mode === 'film') {
      stopWorker(); window.irisDiagnostics.phase = 'film';
      showPoster();
      if (!reducedMotion) playFilm();
      updateFilmReadout();
    } else {
      if (film) film.pause();
      state.dirty = true;
      showPoster();
      $('status').textContent = 'Starting live view';
      // Give the mode change a paint before a potentially expensive compile.
      requestAnimationFrame(() => setTimeout(() => {
        if (state.mode === 'live') initializeLive();
      },0));
    }
    if (message) toast(message,3800);
  }

  function initializeLive() {
    if (state.mode !== 'live') return;
    if (!('Worker' in window) || !('OffscreenCanvas' in window) || !display) {
      fail('Live is unavailable', new Error('This browser needs Worker, OffscreenCanvas and WebGL2. Film and GLSL downloads remain available.'));
      return;
    }
    if (!worker) rebuild();
    if (!animationStarted) { animationStarted = true; requestAnimationFrame(animate); }
  }
  function rebuild() {
    if (state.mode !== 'live') return false;
    stopWorker(); resize(); state.dirty = true; renderedTime = null;
    Object.assign(window.irisDiagnostics,{phase:'preflight',lastError:null,compilerStages:[],lastCompilerStage:null,compileElapsedMs:null});
    liveNotice.textContent = 'Checking Live graphics support.';
    $('status').textContent = 'Checking worker WebGL2';
    const url = URL.createObjectURL(new Blob([$('renderWorker').textContent], {type:'text/javascript'}));
    try { worker = new Worker(url); } catch (error) { fail('Worker unavailable',error); return false; }
    finally { URL.revokeObjectURL(url); }
    const current = worker;
    worker.onmessage = event => {
      const result = event.data;
      if (current !== worker) { if (result.bitmap) result.bitmap.close(); return; }
      if (result.type === 'progress') {
        // Progress is evidence, not completion: it must not cancel the deadline.
        window.irisDiagnostics.lastCompilerStage = result.stage;
        window.irisDiagnostics.compilerStages.push({stage:result.stage,elapsedMs:result.elapsedMs});
        window.irisDiagnostics.compilerStages = window.irisDiagnostics.compilerStages.slice(-8);
        return;
      }
      clearTimeout(deadline);
      if (result.type === 'capabilities') {
        Object.assign(window.irisDiagnostics,{renderer:result.renderer,version:result.version});
        const observedStall = /ANGLE.*Intel.*0x0000A7A8.*Direct3D11/i.test(result.renderer);
        if (observedStall && !allowExperimentalLive) {
          const message = 'This Intel UHD / ANGLE D3D11 adapter stalled during the local audit. Film is available. Driver-version coverage is unknown; an experimental Live attempt may affect the browser even after its worker stops.';
          window.irisDiagnostics.lastError = message;
          window.irisDiagnostics.requiresExplicitAttempt = true;
          stopWorker(); fail('Live requires an explicit attempt',new Error(message));
          liveNotice.textContent = message;
          const attempt = document.createElement('button'); attempt.id = 'experimentalLive'; attempt.textContent = 'Try experimental Live';
          attempt.addEventListener('click',() => { allowExperimentalLive = true; setMode('live'); });
          liveNotice.append(document.createElement('br'),attempt);
          return;
        }
        window.irisDiagnostics.phase = 'compiling';
        liveNotice.textContent = 'Live uses a bounded preview. Film remains available while the GPU compiles.';
        $('status').textContent = 'Compiling in worker · 25s limit';
        worker.postMessage({type:'init',vertex:vertexSource,fragment:fragmentSource()}); armDeadline('Shader compilation',25000);
        return;
      }
      if (result.type === 'error') {
        window.irisDiagnostics.lastError = result.message;
        liveNotice.textContent = result.message;
        stopWorker(); fail('Live unavailable', new Error(result.message)); return;
      }
      if (result.type === 'ready') {
        gl = {}; program = true; busy = false;
        Object.assign(window.irisDiagnostics,{phase:'ready',renderer:result.renderer,parallelCompile:result.parallelCompile,compileElapsedMs:result.compileElapsedMs});
        $('status').textContent = 'Rendering first frame · 15s limit'; state.dirty = true;
      } else if (result.type === 'frame') {
        busy = false;
        // A resized frame can finish after a new viewport request; do not stretch or label it as current.
        if (result.width === canvas.width && result.height === canvas.height) {
          display.drawImage(result.bitmap,0,0); renderedTime = result.time; showRenderedFrame();
          Object.assign(window.irisDiagnostics,{phase:'displaying',frames:window.irisDiagnostics.frames+1,lastFrameMs:result.elapsed,time:result.time});
          liveNotice.textContent = 'Live preview. Animation advances by completed frames; it may run slower than the film.';
          $('status').textContent = `${state.playing ? 'Live' : 'Paused'} · ${Math.round(result.elapsed)} ms / completed frame`;
        }
        result.bitmap.close();
        if (state.playing && !state.seeking && !document.hidden) { state.time = (state.time + 1/24)%duration; state.dirty = true; }
        updateTimeline();
      }
    };
    worker.onerror = error => { window.irisDiagnostics.lastError=error.message; stopWorker(); fail('Worker error',new Error(error.message)); };
    worker.postMessage({type:'probe'}); armDeadline('WebGL capability check',5000);
    return true;
  }

  function resize() {
    if (state.mode !== 'live') { updateFilmReadout(); return; }
    const bounds = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const nativeWidth = Math.max(1,bounds.width*dpr);
    const nativeHeight = Math.max(1,bounds.height*dpr);
    const cap = Math.min(1,1440/Math.max(nativeWidth,nativeHeight));
    const scale = controls.quality.value === 'auto' ? Math.min(1,160/Math.max(nativeWidth,nativeHeight)) : cap*Number(controls.quality.value);
    const width = Math.max(1,Math.round(nativeWidth*scale));
    const height = Math.max(1,Math.round(nativeHeight*scale));
    if (canvas.width !== width || canvas.height !== height) {
      const previousWidth = canvas.width || width;
      const previousHeight = canvas.height || height;
      state.drag[0] *= width/previousWidth;
      state.drag[1] *= height/previousHeight;
      canvas.width = width; canvas.height = height;
      state.dirty = true;
    }

    $('resolution').textContent = `${width} × ${height} · WebGL2`;
  }

  function updatePlay() {
    controls.play.textContent = state.playing ? 'Pause' : 'Play';
    controls.play.setAttribute('aria-label',state.playing ? 'Pause animation' : 'Play animation');
    if (state.mode === 'live' && !state.playing && !state.lost && $('error').hidden) $('status').textContent = 'Paused';
  }

  function updateTimeline() {
    if (!state.seeking) controls.seek.value = String(state.time);
    $('time').textContent = state.time.toFixed(2).padStart(5,'0');
  }

  function draw(delta=0) {
    if (state.mode !== 'live' || !program || !worker || busy || document.hidden) return false;
    busy = true; state.dirty = false;
    worker.postMessage({type:'frame',width:canvas.width,height:canvas.height,time:state.time,delta,frame:state.frame++,mouse:state.mouse,drag:state.drag,scroll:state.scroll});
    armDeadline('Frame rendering',15000); return true;
  }
  function animate() {
    if (state.mode === 'live' && state.dirty) draw(state.playing ? 1/24 : 0);
    requestAnimationFrame(animate);
  }

  function togglePlayback() {
    if (state.mode === 'film' && film) {
      if (film.paused) playFilm(); else film.pause();
      return;
    }
    if (state.lost || !$('error').hidden) return;
    if (state.time >= duration) state.time = 0;
    state.playing = !state.playing;
    state.previousTime = 0; state.measuredStart = 0; state.measuredFrames = 0;
    state.dirty = true; updatePlay();
  }

  function pointerPosition(event) {
    const rect = canvas.getBoundingClientRect();
    return [(event.clientX-rect.left)*canvas.width/rect.width,
            (rect.bottom-event.clientY)*canvas.height/rect.height];
  }

  canvas.addEventListener('pointerdown',event => {
    if (event.button !== 0) return;
    state.pointer = event.pointerId;
    canvas.setPointerCapture(event.pointerId);
    state.lastPointer = pointerPosition(event);
    state.mouse = [...state.lastPointer,Math.max(.01,state.lastPointer[0]),Math.max(.01,state.lastPointer[1])];
    canvas.classList.add('dragging'); state.dirty = true;
  });
  canvas.addEventListener('pointermove',event => {
    const position = pointerPosition(event);
    state.mouse[0] = position[0]; state.mouse[1] = position[1];
    if (state.pointer === event.pointerId) {
      state.drag[0] += position[0]-state.lastPointer[0];
      state.drag[1] += position[1]-state.lastPointer[1];
      state.lastPointer = position; state.dirty = true;
    }
  });
  function releasePointer(event) {
    if (state.pointer !== event.pointerId) return;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    state.pointer = null; state.mouse[2] = -Math.abs(state.mouse[2]); state.mouse[3] = -Math.abs(state.mouse[3]);
    canvas.classList.remove('dragging'); state.dirty = true;
  }
  canvas.addEventListener('pointerup',releasePointer);
  canvas.addEventListener('pointercancel',releasePointer);
  canvas.addEventListener('wheel',event => {
    event.preventDefault();
    const delta = event.deltaY*(event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? innerHeight : 1);
    state.scroll = Math.max(-2,Math.min(2,state.scroll+delta*.001)); state.dirty = true;
  },{passive:false});

  controls.play.addEventListener('click',togglePlayback);
  controls.quality.addEventListener('change',resize);
  controls.samples.addEventListener('change',rebuild);
  controls.seek.addEventListener('pointerdown',() => { state.seeking = true; });
  controls.seek.addEventListener('input',() => {
    state.time = Number(controls.seek.value); state.dirty = true;
    $('time').textContent = state.time.toFixed(2).padStart(5,'0');
  });
  function releaseSeek() { state.seeking = false; state.previousTime = 0; }
  controls.seek.addEventListener('change',releaseSeek);
  controls.seek.addEventListener('pointerup',releaseSeek);
  controls.seek.addEventListener('pointercancel',releaseSeek);
  controls.reset.addEventListener('click',() => {
    state.time = 0; state.frame = 0; state.drag = [0,0]; state.scroll = 0;
    state.mouse = [0,0,-1,-1]; state.dirty = true; state.previousTime = 0;
    updateTimeline(); toast('Time and camera reset');
  });

  function download(blob,name) {
    const href = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href = href; link.download = name;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(href),1000);
  }
  $('save').addEventListener('click',() => {
    if (state.mode === 'film' && film && film.readyState >= 2) {
      try {
        const snapshot = document.createElement('canvas');
        snapshot.width = film.videoWidth; snapshot.height = film.videoHeight;
        const context = snapshot.getContext('2d');
        if (!context) throw new Error('Image export is unavailable.');
        context.drawImage(film,0,0);
        const exportTime = film.currentTime.toFixed(2);
        snapshot.toBlob(blob => {
          if (!blob) { toast('PNG export failed'); return; }
          download(blob,`IRIS-09-film-${exportTime}s.png`); toast('Film frame saved');
        },'image/png');
        return;
      } catch(error) { toast('Saving the rendered poster instead.'); }
    }
    if (renderedTime === null || state.mode !== 'live') {
      if (poster) {
        const link = document.createElement('a'); link.href = poster.src;
        const extension = poster.src.startsWith('data:image/jpeg') ? 'jpg' : poster.src.startsWith('data:image/webp') ? 'webp' : 'png';
        link.download = `IRIS-09-poster.${extension}`;
        document.body.appendChild(link); link.click(); link.remove();
        toast('Rendered poster saved');
      }
      return;
    }
    const exportTime = renderedTime.toFixed(2);
    canvas.toBlob(blob => {
      if (!blob) { toast('PNG export failed'); return; }
      download(blob,`IRIS-09-${exportTime}s.png`); toast('PNG saved');
    },'image/png');
  });
  $('download').addEventListener('click',() => {
    download(new Blob([source],{type:'text/plain;charset=utf-8'}),'IRIS-09.glsl');
  });
  const bytes = new TextEncoder().encode(shareSource);
  let binary = '';
  for (let i=0;i<bytes.length;i+=32768) binary += String.fromCharCode(...bytes.subarray(i,i+32768));
  const encoded = btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
  $('fragcoord').href = `https://fragcoord.xyz/#code=${encoded}`;

  $('retry').addEventListener('click',() => setMode('live'));
  window.addEventListener('resize',resize);
  document.addEventListener('visibilitychange',() => {
    state.previousTime = 0; state.measuredStart = 0; state.measuredFrames = 0;
    if (!document.hidden && state.mode === 'live') state.dirty = true;
  });
  window.addEventListener('keydown',event => {
    if (event.code === 'Space' && !/INPUT|SELECT|BUTTON|A/.test(document.activeElement.tagName)) {
      event.preventDefault(); togglePlayback();
    }
  });
  if (film) {
    $('modeSwitch').hidden = false;
    film.muted = true; film.loop = true; film.playsInline = true; film.autoplay = !reducedMotion;
    if (poster) film.poster = poster.src;
    if (reducedMotion) film.pause();
    ['loadedmetadata','play','pause','ended'].forEach(name => film.addEventListener(name,updateFilmReadout));
    film.addEventListener('loadeddata',() => { film.classList.remove('unavailable'); updateFilmReadout(); });
    film.addEventListener('error',() => {
      film.classList.add('unavailable');
      if (state.mode === 'film') {
        showPoster();
        $('status').textContent = 'Rendered poster';
        $('resolution').textContent = 'Film playback unavailable';
        toast('The embedded film cannot play in this browser. The poster and source are available.',4500);
      }
    });
    $('filmMode').addEventListener('click',() => setMode('film'));
    $('liveMode').addEventListener('click',() => setMode('live'));
    setMode('film');
  } else {
    initializeLive();
  }
})();
