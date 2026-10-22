"""Reference shader and acceptance-rule checks; never create a GPU context."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from iris_native import shaders
import validate_native


class NativeValidatorTests(unittest.TestCase):
    def test_reference_keeps_original_aa_camera_loop_and_function_bodies(self):
        original = shaders.ARCHIVE.read_text(encoding='utf-8')
        for dispersion in shaders.DISPERSIONS:
            generated, retained = validate_native.reference_shader(dispersion, original)
            restored = generated.replace('cybr_scalar_noise2', 'noise2').replace('cybr_scalar_noise3', 'noise3')
            self.assertIn('for(int y=0;y<AA;y++)', restored)
            self.assertIn('for(int x=0;x<AA;x++)', restored)
            self.assertIn('color+=shadeRay(ro,rd);', restored)
            self.assertEqual(restored.count('color/=float(AA*AA);'), 1)
            self.assertNotIn('u_sampleIndex', restored)
            self.assertNotIn('u_dispersion', restored)
            self.assertNotIn('#define CAPTURE', restored)
            self.assertNotIn('color*=0.96', restored)
            checked = 0
            for name, _, _, body in shaders.function_regions(original):
                if name in retained and name not in ('main', 'shadeRay'):
                    self.assertIn(body, restored, name)
                    checked += 1
            self.assertGreaterEqual(checked, 50)

    def test_reference_rejects_changed_original_calls(self):
        original = shaders.ARCHIVE.read_text(encoding='utf-8')
        changed = original.replace('vec3 r=opticalTransport(ro,rd,h,-0.0030);', 'vec3 r=vec3(0);')
        with self.assertRaises(ValueError):
            validate_native.reference_shader(0., changed)

    def test_finite_and_error_limits_are_enforced(self):
        validate_native.require_equivalence(True, 0.)
        validate_native.require_equivalence(True, 2.384185791015625e-7)
        validate_native.require_equivalence(True, 1e-5)
        for finite, error in ((False, 0.), (True, float('nan')), (True, float('inf')), (True, 1.0001e-5)):
            with self.assertRaises(AssertionError):
                validate_native.require_equivalence(finite, error)


if __name__ == '__main__':
    unittest.main()
