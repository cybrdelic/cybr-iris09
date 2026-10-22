# Explicit native macOS software rendering

The first macOS 15 ARM hosted run created an `Apple Software Renderer` CGL
context. All shaders compiled in under a second, but the first transport draw
exceeded the 60-second process limit. The failure is preserved in
[job 120125896055](https://github.com/cybrdelic/cybr-iris09/actions/runs/39865305305/job/120125896055).
That result is not a successful Mac render.

An explicit Mesa EGL backend is provided for machines where that CGL path is
unusable. Install a native Mesa build with EGL and llvmpipe (the hosted workflow
uses Homebrew), then select it in the shell running IRIS:

```sh
brew install mesa
export CYBR_EGL_LIBRARY="$(brew --prefix mesa)/lib/libEGL.dylib"
export CYBR_IRIS_GL_BACKEND=mesa
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export LP_NUM_THREADS=4
python tools/render_native.py --width 128 --height 72 --samples 2 --timeout 60 --output iris.png
python tools/serve_native.py --timeout 60
```

This is CPU software execution of the same OpenGL shaders, not Metal or a
physical Mac GPU claim. Dimensions, AA2's four camera samples, three wavelengths,
24 transport iterations, scene geometry and the numerical comparison gate are
unchanged. Backend choice is explicit; a Mesa setup failure does not silently
fall back to CGL. Without the selector the prior native backend order remains.
The Python runtime only discovers installed libraries and never installs or
reconfigures drivers. An explicit library path must already exist and be
absolute. Shared-library discovery follows the owned CYBR FIRE helper at
`3b8a848ad27685c0788057eebab5b9878631fa86`; no additional dependency license is
introduced by this adapter.

The adapter implements ModernGL's
[existing context loader interface](https://github.com/moderngl/moderngl/blob/5.13.0/src/gl_methods.hpp)
with EGL function addresses and owns context cleanup. Mocked lifetime/selection
tests establish protocol behavior only. The native workflow runs unchanged
AA1/AA2 renders, independent original-shader numerical comparisons and two real
HTTP render requests; passing hosted results are required before claiming this
path works on macOS. The prior Linux native run passed all those checks.

## Recorded hosted results

[Native run 39866943666](https://github.com/cybrdelic/cybr-iris09/actions/runs/39866943666), at source commit `03d56b37a7d5dbd9570cea44bba15c0eef6842bf`, passed both operating systems. This repeats the first successful [Mesa adapter run 39866583188](https://github.com/cybrdelic/cybr-iris09/actions/runs/39866583188) at `f2547ca724c45d04a55b326e54c811ac7a6f4f8b`:

| Actual backend | Native renders | Original-equation comparison | Real HTTP preview |
| --- | --- | --- | --- |
| macOS 15 ARM64, Mesa 26.2.2 llvmpipe LLVM 23.1.0 | 128 x 72 AA2 and 159 x 91 AA1 passed | 331,776 finite values, max error 0.0, fixed 1e-5 gate | Two 160 x 90 AA2 frames; 13,533 changed pixels; clean shutdown |
| Ubuntu 24.04, Mesa llvmpipe LLVM 20.1.2 | Same dimensions and samples passed | Same count, max error 0.0 and gate | Same dimensions, samples and changed-pixel count; clean shutdown |

The first Mac Mesa HTTP requests took approximately 1.13 and 1.01 seconds including process startup. These small software-rendered frames do not establish high-resolution performance, physical Mac GPU coverage, or browser Live. The failed Apple software CGL result above remains valid for that backend. Viewer preflight now warns before the separately observed macOS SwiftShader Live stall; that guard does not repair Live rendering.
