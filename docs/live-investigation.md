# Live compilation investigation

Local Windows investigation on 22 October 2026, against viewer commit
`30763de609a87ab136e761814b1d399910b24f75`.

**Live remains unresolved on the tested Intel UHD adapter.** None of the three
bounded experiments produced a completed Live frame. Film playback is a separate,
previously verified presentation path. Historical images and film were not used
as evidence of current shader execution.

## What failed

The earlier worker timeout occurred before `ready`, so it did not establish a
ray-marching or GPU tile-execution problem. The final instrumented browser attempt
returned from the JavaScript `compileShader` and `linkProgram` calls, then waited
for `KHR_parallel_shader_compile` completion for the entire 25-second budget.
It never reached shader-status queries, readiness, a draw submission or bitmap
transfer. These asynchronous API returns do not mean compilation succeeded.

Native OpenGL also failed to finish compiling within its process budget. The
evidence therefore does not isolate the issue to ANGLE. Compiler expansion of
the large nested shading graph is a plausible explanation, but the measurements
cannot distinguish ANGLE translation, HLSL compilation or driver program creation.

## Bounded experiments

| Attempt | Input and backend | Observed result |
| --- | --- | --- |
| 1 | Original equations, desktop GLSL 330 preamble; `noise3` namespaced | WGL context succeeded. Compilation failed in 54 ms because the remaining user-defined `noise2` collides with a desktop GLSL built-in return type. No draw. |
| 2 | Original equations; both `noise2` and `noise3` namespaced | WGL context ready at 1.873 s; compile/link began at 1.878 s. The process was stopped at 45 s without a linked program or draw. |
| 3 | Derived, structurally refactored equations; Chrome WebGL2 / ANGLE D3D11 | Compile/link calls returned, but asynchronous completion did not arrive within 25 s. Returned to Film; zero Live frames. |

The native backend reported `Intel(R) UHD Graphics`, OpenGL
`3.3.0 - Build 31.0.101.4146`. The browser reported Chrome 145 and
`ANGLE (Intel, Intel(R) UHD Graphics (0x0000A7A8) Direct3D11 vs_5_0 ps_5_0, D3D11)`.
Browser settings were a 1280×720 viewport, a 960×540 canvas and `AA=2` (four camera
samples). The native frame request used the same canvas and sample count; neither
native attempt reached it.

The third attempt preserved all original ray-march, bounce, light, quadrature,
blade and camera-sample counts. Its changes moved successful-hit normal evaluation
outside the march, deferred terminal opaque shading behind an explicit flag,
replaced three transport call sites with one ordered wavelength loop, and supplied
the original loop bounds as uniforms. Full RGB throughput and termination rules
were retained. An independent static review found no algorithmic change, but
pixel equivalence could not be tested because neither original nor derived code
completed a frame. **The derived shader is an external diagnostic experiment; it
is not included in the deliverable runtime.**

One browser harness setup timed out while trying to select a hidden Film-mode
control. It never requested Live or created a WebGL context. That setup issue was
corrected before attempt 3 and is not an additional GPU attempt.

## Responsiveness and verification limits

During attempt 3, a real Play control click completed in **19.59 ms**. The largest
gap in a 20 ms main-thread heartbeat was **79.90 ms** over approximately 25.8 s.
These support DOM/control responsiveness during this attempt; they do not prove
smooth animation or screenshot presentation. No Live pixel capture was possible.
The owned browser closed normally after the timeout. Worker termination alone is
not proof that a driver compiler has cancelled outstanding work.

No fourth GPU attempt was made. No physical mobile device, other Windows driver,
macOS or Linux GPU was tested in this investigation. No quality reduction,
replacement scene or prerendered media was substituted for Live.

## Preserved source and diagnostic changes

Original Git blobs remain:

- `IRIS-09.glsl`: `47637b782090089d04f455f8befe371319fe25c7`
- `IRIS-09-fragcoord.glsl`: `98dfbc888a57049b6bf7ae0183acc852f59e5515`

Both embedded original source strings are unchanged. The readable shader's
normalized UTF-8 SHA-256 is
`455e1ba9b0740a6ab925f9c022eea5f217fd3bbfc08ffec3177fb3b1d925843b`.

The viewer now records timestamped compiler stages in `window.irisDiagnostics`,
without extending or cancelling its deadline when progress arrives. It clears
stale failure details on an explicit new attempt. Shader equations, render order,
sample controls, adapter warning, historical media and licenses are unchanged.

Four offline unit checks pass, including mock-GL tests for incomplete compilation,
readiness ordering and compile-error propagation. Mock GL is a protocol check,
not execution verification. No GPU run was added after the three-attempt budget.
Machine-readable observations are in [live-investigation.json](live-investigation.json).
