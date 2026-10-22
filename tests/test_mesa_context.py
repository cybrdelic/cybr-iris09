"""Backend selection and resource lifetime contracts; no GPU proof is implied."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from iris_native import egl_library, mesa_context, renderer


class MesaContracts(unittest.TestCase):
    def test_explicit_selection_uses_mesa_and_never_silently_falls_back(self):
        factory = Mock()
        with patch.dict(os.environ, {'CYBR_IRIS_GL_BACKEND': 'mesa'}):
            with patch.object(mesa_context, 'create_mesa_context', return_value='context') as create:
                self.assertEqual(renderer.create_context(factory), ('context', 'mesa-egl-surfaceless', []))
                create.assert_called_once_with(factory)
            with patch.object(mesa_context, 'create_mesa_context', side_effect=RuntimeError('missing Mesa')):
                with self.assertRaisesRegex(RuntimeError, 'missing Mesa'):
                    renderer.create_context(factory)
        factory.assert_not_called()

    def test_invalid_selection_does_not_create_context(self):
        factory = Mock()
        with patch.dict(os.environ, {'CYBR_IRIS_GL_BACKEND': 'unknown'}):
            with self.assertRaises(ValueError):
                renderer.create_context(factory)
        factory.assert_not_called()

    def test_loader_lifetime_transfers_to_modern_gl_or_cleans_failed_factory(self):
        loader = Mock()
        factory = Mock(return_value='modern context')
        self.assertEqual(mesa_context.create_mesa_context(factory, lambda: loader), 'modern context')
        factory.assert_called_once_with(require=330, context=loader)
        loader.release.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, 'factory failed'):
            mesa_context.create_mesa_context(Mock(side_effect=RuntimeError('factory failed')), lambda: loader)
        loader.release.assert_called_once()

    def test_release_unbinds_destroys_terminates_once(self):
        loader = mesa_context.MesaContext.__new__(mesa_context.MesaContext)
        loader.display, loader.context, loader.egl = 123, 456, Mock()
        loader.release()
        loader.egl.eglMakeCurrent.assert_called_once_with(123, None, None, None)
        loader.egl.eglDestroyContext.assert_called_once_with(123, 456)
        loader.egl.eglTerminate.assert_called_once_with(123)
        self.assertIsNone(loader.context)
        self.assertIsNone(loader.display)
        loader.release()
        loader.egl.eglTerminate.assert_called_once()

    def test_partial_open_failure_releases_initialized_display(self):
        def fail_open(loader):
            loader.display, loader.context, loader.egl = 123, None, fake
            raise RuntimeError('no configuration')
        fake = Mock()
        with patch.object(mesa_context.MesaContext, '_open', fail_open):
            with self.assertRaisesRegex(RuntimeError, 'no configuration'):
                mesa_context.MesaContext()
        fake.eglTerminate.assert_called_once_with(123)
        fake.eglDestroyContext.assert_not_called()

    def test_loader_returns_integer_zero_for_missing_optional_function(self):
        loader = mesa_context.MesaContext.__new__(mesa_context.MesaContext)
        loader.egl = Mock()
        loader.egl.eglGetProcAddress.return_value = None
        self.assertEqual(loader.load_opengl_function('glOptional'), 0)
        loader.egl.eglGetProcAddress.assert_called_once_with(b'glOptional')

    def test_explicit_library_requires_existing_absolute_file_without_fallback(self):
        with patch.dict(os.environ, {'CYBR_EGL_LIBRARY': 'relative/libEGL'}):
            with self.assertRaisesRegex(RuntimeError, 'existing absolute'):
                list(egl_library.library_candidates())
        with tempfile.TemporaryDirectory() as folder:
            library = Path(folder) / 'libEGL.dylib'
            library.write_bytes(b'not a real library')
            with patch.dict(os.environ, {'CYBR_EGL_LIBRARY': str(library)}):
                self.assertEqual(list(egl_library.library_candidates()), [(str(library), 'explicit')])
                with self.assertRaisesRegex(RuntimeError, 'No fallback'):
                    egl_library.load_egl_library()


if __name__ == '__main__':
    unittest.main()
