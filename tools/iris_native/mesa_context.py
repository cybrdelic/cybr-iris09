"""Explicit surfaceless EGL loader for ModernGL, including native macOS Mesa.

Context creation follows the owned CYBR FIRE EGL backend. Only API loading is
adapted: every IRIS shader, sample, render target and numerical gate is shared.
No dependency is installed and no fallback is hidden inside this module.
"""
import ctypes as C
from .egl_library import load_egl_library


class MesaContext:
    standalone = True

    def __init__(self):
        self.display = self.context = None
        try:
            self._open()
        except Exception:
            self.release()
            raise

    def _open(self):
        self.egl, self.library_info = load_egl_library()
        e = self.egl
        # Declare cleanup before creating anything so partial failures are safe.
        e.eglTerminate.argtypes = [C.c_void_p]
        e.eglTerminate.restype = C.c_uint
        e.eglDestroyContext.argtypes = [C.c_void_p, C.c_void_p]
        e.eglDestroyContext.restype = C.c_uint
        e.eglMakeCurrent.argtypes = [C.c_void_p] * 4
        e.eglMakeCurrent.restype = C.c_uint
        e.eglGetProcAddress.argtypes = [C.c_char_p]
        e.eglGetProcAddress.restype = C.c_void_p
        pointer = e.eglGetProcAddress(b'eglGetPlatformDisplayEXT')
        if not pointer:
            raise RuntimeError('EGL_EXT_platform_base is unavailable')
        get_display = C.CFUNCTYPE(C.c_void_p, C.c_uint, C.c_void_p, C.POINTER(C.c_int))(pointer)
        display = get_display(0x31DD, None, None)  # EGL_PLATFORM_SURFACELESS_MESA
        e.eglInitialize.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int)]
        e.eglInitialize.restype = C.c_uint
        major, minor = C.c_int(), C.c_int()
        if not display or not e.eglInitialize(display, C.byref(major), C.byref(minor)):
            raise RuntimeError('Cannot initialize a surfaceless Mesa EGL display')
        self.display = display
        e.eglBindAPI.argtypes = [C.c_uint]
        e.eglBindAPI.restype = C.c_uint
        if not e.eglBindAPI(0x30A2):  # EGL_OPENGL_API
            raise RuntimeError('Cannot bind desktop OpenGL through EGL')
        attributes = (C.c_int * 7)(0x3033, 1, 0x3040, 8, 0x3024, 8, 0x3038)
        config, count = C.c_void_p(), C.c_int()
        e.eglChooseConfig.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_void_p), C.c_int, C.POINTER(C.c_int)]
        e.eglChooseConfig.restype = C.c_uint
        if not e.eglChooseConfig(display, attributes, C.byref(config), 1, C.byref(count)) or count.value < 1:
            raise RuntimeError('No surfaceless EGL OpenGL configuration')
        context_attributes = (C.c_int * 7)(0x3098, 3, 0x30FB, 3, 0x30FD, 1, 0x3038)
        e.eglCreateContext.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.POINTER(C.c_int)]
        e.eglCreateContext.restype = C.c_void_p
        self.context = e.eglCreateContext(display, config, None, context_attributes)
        if not self.context:
            raise RuntimeError('Mesa OpenGL 3.3 core context unavailable')
        self.__enter__()

    def load_opengl_function(self, name):
        # ModernGL expects an integer address, including zero for unavailable
        # optional extensions. Its required-function checks remain authoritative.
        return self.egl.eglGetProcAddress(name.encode('ascii')) or 0

    def __enter__(self):
        if not self.context or not self.egl.eglMakeCurrent(self.display, None, None, self.context):
            raise RuntimeError('Cannot make the Mesa EGL context current')
        return self

    def __exit__(self, *args):
        if self.display:
            self.egl.eglMakeCurrent(self.display, None, None, None)

    def release(self):
        if not self.display:
            return
        if self.context:
            self.__exit__()
            self.egl.eglDestroyContext(self.display, self.context)
            self.context = None
        self.egl.eglTerminate(self.display)
        self.display = None


def create_mesa_context(factory, loader_factory=MesaContext):
    loader = loader_factory()
    try:
        return factory(require=330, context=loader)
    except Exception:
        loader.release()
        raise
