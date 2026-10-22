# Live pass investigation

The complete IRIS scene now renders through the [native OpenGL renderer](native-renderer.md). Browser GPU Live remains unresolved on the tested Windows Intel UHD / ANGLE D3D11 adapter. The original viewer and archived GLSL remain unchanged by the experiments described here.

This continues the [initial compilation investigation](live-investigation.md). The new work separated geometry, opaque lighting and optical transport to identify the compiler boundary, then built state passes retaining the original equations. No scene, camera sample, wavelength, optical iteration or lighting effect was removed.

## Numerical checks

The reference programs retain the original full-RGB transport at each of the three original dispersion values. Four snapshots exercise times 0, 2.5, 5 and 9.9 seconds, including camera drag and zoom. Comparisons use linear float32 RGB, all four AA2 camera samples and the original addition order. `CAPTURE` is never enabled merely to obtain linear output.

| Candidate | Compared RGB components | Maximum absolute difference | Fixed tolerance | Result |
| --- | ---: | ---: | ---: | --- |
| Combined opaque intersection and shading passes | 331,776 | 2.384185791e-7 | 1e-5 | Pass |
| Terminal-only opaque intersection closure | 331,776 | 2.384185791e-7 | 1e-5 | Pass |
| Additional terminal guards and early returns | 331,776 | 2.819299698e-5 | 1e-5 | Rejected |

All compared values were finite. The accepted comparisons completed in 9.74 and 11.50 seconds on native Intel OpenGL, with explicit completion after each stage. These are small 128x72 diagnostic frames, not a film or hardware performance qualification. The rejected variant was not submitted to another browser test.

The pass experiments retain the first optical hit, full RGB throughput and cutoff, 24 transport updates, reflected-ray offsets, and the distinction between the initial environment miss and later transport misses. Keeping each opaque intersection with its shading calculation removed the earlier numerical discrepancy. Earlier rare 4x4 outliers already existed in initialization pixels and were subsequently copied exactly; that observation does not establish driver corruption.

## Actual browser result

Both numerically passing candidates were tested in Chrome 145 at the viewer's explicit Auto160 setting, a 160x90 canvas and AA2. A real WebGL2 worker compiled initialization, scene intersection and reflected lighting. The remaining terminal shading program did not report asynchronous compile/link completion within its separate 25-second limit. The total compile budget was 60 seconds and the frame budget was 15 seconds; progress never reset either deadline.

| Browser candidate | Initialization complete | Scene complete | Reflected lighting complete | Terminal shading |
| --- | ---: | ---: | ---: | --- |
| Combined passes | 2.50 s | 8.17 s | 14.70 s | 25 s timeout |
| Terminal opaque closure | See timestamped receipt | 8.41 s | 15.33 s | 25 s timeout |

Completion times are cumulative from compilation start, except the terminal per-program timeout. **Neither browser probe reached a draw or produced a completed Live frame.** Film fallback became visible, and the main-thread heartbeat's largest gaps were 158 and 143 ms. This supports responsive controls during these attempts, not smooth rendered animation.

The measurements identify a particular program boundary. They do not establish whether ANGLE translation, HLSL optimization or driver program creation is responsible. Native success does not prove browser numerical equivalence. No physical mobile GPU or other Windows driver was qualified.

## Preserved deliverable

The numerically validated [native renderer](native-renderer.md) remains the working execution path. Experimental pass shaders have not been integrated into the production browser viewer. No historical film pixels were passed off as newly rendered output, and no license or archived shader was changed.

Exact program hashes, stages, renderer metadata and numerical results are recorded in [live-pass-investigation.json](live-pass-investigation.json). The private task workspace retains the individual experiment sources and raw arrays; this receipt does not imply those experimental generators are part of the supported viewer runtime.
