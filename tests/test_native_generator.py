"""CPU-only invariants for the split renderer; these do not certify a GPU."""
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from iris_native import shaders
from iris_native.renderer import context_candidates, create_context
import render_native


class NativeShaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = shaders.ARCHIVE.read_text(encoding='utf-8')

    def test_retained_scene_function_bodies_are_archival(self):
        for aa in (1, 2):
            generated, retained = shaders.transport(aa)
            restored = generated.replace('cybr_scalar_noise2', 'noise2').replace('cybr_scalar_noise3', 'noise3')
            original_functions = shaders.function_regions(self.original)
            preserved = 0
            for name, _, _, body in original_functions:
                if name in retained and name != 'main':
                    self.assertIn(body, restored, name)
                    preserved += 1
            self.assertGreaterEqual(preserved, 50)
            self.assertIn('for(int bounce=0;bounce<24;bounce++)', restored)
            self.assertIn('return opticalTransport(ro,rd,h,u_dispersion);', restored)
            self.assertIn('environment(ro,rd,0.25)', restored)
            self.assertNotIn('vec3 shadeRay(', restored)

    def test_sample_index_preserves_camera_and_light_phase(self):
        for aa in (1, 2):
            generated, _ = shaders.transport(aa)
            self.assertIn(f'#define AA {aa}\n', generated)
            self.assertIn('int y=u_sampleIndex/AA;\n    int x=u_sampleIndex%AA;', generated)
            self.assertIn('seed=float(x+y*AA);', generated)
            self.assertIn('lightPhase=int(seed)%4;', generated)
            self.assertNotRegex(generated, r'for\s*\(\s*int\s+[xy]\s*=')
            self.assertNotIn('color/=float(AA*AA);', generated)
            self.assertEqual(generated.count('color=wavelengthRay(ro,rd);'), 1)
            self.assertIn('#error Native split requires the original non-CAPTURE sampling', generated)
            self.assertEqual([(index % aa, index // aa) for index in range(aa*aa)],
                             [(x, y) for y in range(aa) for x in range(aa)])

    def test_composition_uses_original_display_equations_once(self):
        for aa in (1, 2):
            result = shaders.composition(aa)
            self.assertIn(f'#define AA {aa}\n', result)
            self.assertEqual(result.count('color/=float(AA*AA);'), 1)
            for line in ('color*=0.96*(1.0-0.075*dot(st,st));',
                         'color=pow(aces(max(color,0.0)),vec3(1.0/2.2));',
                         'color+=(hash12(gl_FragCoord.xy)-0.5)/700.0;',
                         'fragColor=vec4(sat(color),1.0);'):
                self.assertIn(line, self.original)
                self.assertEqual(result.count(line), 1)
            self.assertIn('texelFetch(u_red,pixel,0).r,texelFetch(u_green,pixel,0).g,texelFetch(u_blue,pixel,0).b', result)
        self.assertIn('texelFetch(u_previousSum,pixel,0)+texelFetch(u_sample,pixel,0)', shaders.accumulation())

    def test_changed_archive_structure_fails_loudly(self):
        for old in ('void main() {', '    vec3 color=vec3(0);',
                    '        color+=shadeRay(ro,rd);'):
            with self.assertRaises(ValueError):
                shaders.transport(original=self.original.replace(old, '/* recognized region removed */'))
        for invalid in (0, 3, 1.0, True):
            with self.assertRaises(ValueError):
                shaders.transport(invalid)


class NativeSetupTests(unittest.TestCase):
    def test_backend_selection_and_linux_fallback(self):
        self.assertEqual(context_candidates('Windows'), [('wgl-default', {})])
        self.assertEqual(context_candidates('Darwin'), [('cgl-default', {})])
        calls = []
        def factory(**arguments):
            calls.append(arguments)
            if 'backend' in arguments:
                raise RuntimeError('test EGL unavailable')
            return 'mock context'
        context, backend, attempts = create_context(factory, 'Linux')
        self.assertEqual(context, 'mock context')
        self.assertEqual(backend, 'default')
        self.assertEqual(calls, [{'require': 330, 'backend': 'egl'}, {'require': 330}])
        self.assertEqual(attempts, [{'backend': 'egl', 'error': 'test EGL unavailable'}])

    def test_invalid_sizes_and_existing_output_rejected_before_gpu(self):
        options = render_native.parser().parse_args(['--width', '0'])
        with self.assertRaises(ValueError):
            render_native.validate(options)
        options = render_native.parser().parse_args(['--width', '8192', '--height', '8192'])
        with self.assertRaises(ValueError):
            render_native.validate(options)
        with tempfile.TemporaryDirectory() as folder:
            existing = Path(folder) / 'existing.png'
            existing.write_bytes(b'keep')
            options = render_native.parser().parse_args(['--output', str(existing)])
            with self.assertRaises(ValueError):
                render_native.validate(options)
            self.assertEqual(existing.read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
