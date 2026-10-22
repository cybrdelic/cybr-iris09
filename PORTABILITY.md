# Viewer setup and limits

The self-contained HTML includes the original shader, compact share source, film and poster. Serve it on Windows, macOS or Linux:

```sh
python -m http.server 8000
```

Open `http://localhost:8000/IRIS-09-viewer.html`. Film is the default and is the reliable presentation path on GPUs that cannot compile the large Live shader. Film playback is historical render evidence, not proof of current Live execution.

Live requires WebGL2 inside a Worker/OffscreenCanvas. Compilation and GPU submission run outside the UI thread. One frame is in flight at a time; 32-pixel scissors preserve full-frame shader coordinates and equations while limiting each GPU submission. Compilation has a 25-second deadline and a frame has a 15-second deadline; failure returns to Film with a persistent reason. Browser/driver GPU work already submitted may still take time to unwind. Select Live to retry; there is no automatic retry loop.

Auto preview starts at a 160-pixel long edge with one camera sample. Full resolution and four-sample controls remain explicit choices; Auto is not a full-quality film rendering claim. Animation advances by 1/24 second per completed frame, so expensive frames slow playback rather than queueing unbounded work. PNG export labels the last completed Live frame's time. A viewport change discards an obsolete-sized frame. Hidden tabs stop new submissions.

On the audited Windows Intel UHD / Chrome ANGLE session, the original main-thread Live implementation timed out even at a 160×120 diagnostic size. The worker implementation returned its DOM state to Film after the deadline without a verified Live frame, but presentation remained delayed: terminating a worker does **not** guarantee cancellation inside the GPU driver. Preflight therefore shows a visible warning for the specifically observed Intel device ID `0x0000A7A8` through ANGLE Direct3D11, before compiling. An explicit **Try experimental Live** button remains available. This is not a blanket statement about Intel GPUs: driver-version coverage is unknown, and other adapters are not automatically blocked. This unresolved driver/compiler limitation is not proof that the GLSL is invalid. No physical iOS/Android device or macOS GPU has been tested locally. Responsive viewport checks do not imply that testing.

Maintain the JavaScript in `viewer/runtime.js` and `viewer/worker.js`, then embed it with:

```sh
python tools/build_viewer.py
python -m unittest discover -s tests -v
python -m pip install playwright==1.63.0
python -m playwright install chromium
python tests/browser_smoke.py
```

The builder preserves shader and media payloads. Browser results record either a completed Live frame or the exact fallback reason; a fallback never counts as Live rendering success. The three-OS CI workflow checks that distinction. Remote CI remains unverified until a branch is pushed and CI runs. Source and media licenses are unchanged.

The [bounded Live investigation](docs/live-investigation.md) records three further attempts with original equations and full four-sample quality. Native compilation and an equivalent structured browser variant both timed out before drawing; Live remains unresolved on the tested adapter. The viewer now exposes compiler-stage timing in `window.irisDiagnostics`. Progress messages never extend the deadline. The experimental derived shader is kept outside the viewer; original shader files and embedded downloads remain unchanged.

## Native full-scene execution

A subsequent decomposition isolates camera samples and wavelengths without removing any scene features, optical iterations or light samples. The [native renderer](docs/native-renderer.md) successfully renders through Windows WGL with the audited Intel GPU. Its AA2 linear output was compared with original constant-wavelength reference programs at four camera/time snapshots; all 331,776 values were finite, with maximum absolute difference 2.384185791e-7. This supports native numerical agreement on that driver, not browser or cross-device equivalence.

The packaged command was also executed at 128 x 72 with four camera samples and at an explicitly selected 159 x 91 with one sample, a different time and camera. macOS/Linux native execution and physical mobile GPUs remain untested. The browser's default ANGLE/D3D11 backend can compile and render the geometry and opaque-lighting diagnostic closures, but the full transport program still reaches its compilation deadline. The separate diagnostic subsets are not substituted for full Live.

The subsequent [pass investigation](docs/live-pass-investigation.md) narrowed the browser cutoff: initialization, scene intersection and reflected lighting compiled, but terminal shading reached its 25-second asynchronous compile/link limit. Neither passing native decomposition produced a browser GPU frame. These experiments remain outside the production viewer.

The [localhost native preview](docs/native-preview.md) is a separate working interactive still path. Actual Windows browser controls produced new native AA2 pixels after time, drag and zoom changes, and discarded a superseded response. Measured requests took 8-12 seconds including process startup and compilation. A 390-pixel layout check passed; that does not establish physical-phone GPU compatibility or real-time rendering.

The first hosted Linux native run passed both renders, independent numerical validation and the real HTTP smoke. The first macOS CGL run compiled successfully but timed out drawing through Apple's software renderer. The [explicit native Mesa backend](docs/native-macos-mesa.md) provides a software OpenGL alternative with unchanged equations, samples and test gates; its actual macOS CI result is tracked separately from the preserved CGL failure.

The macOS hosted Chromium 153 viewer reported ANGLE SwiftShader (LLVM 10.0.0, device 0x0000C0DE). It compiled the shader but hit the ten-second tile limit with zero frames, and later browser interaction was delayed. That observed macOS/software-renderer combination now uses the same explicit experimental-attempt prompt as the previously observed Intel adapter. Other Mac GPUs and SwiftShader versions are not inferred to fail. The original Live implementation remains available through the explicit button; this guard restores usable controls and does not count as a Live rendering fix.
