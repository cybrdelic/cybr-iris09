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
