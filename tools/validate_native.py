"""Optional, 60-second native GPU comparison against original whole-AA probes.

This checks the complete RGB output of all three wavelengths at four camera
snapshots. It is deliberately separate from dependency-free CPU unit tests.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

from iris_native import shaders

TIMEOUT_SECONDS = 60
MAX_ABSOLUTE_ERROR = 1e-5
SNAPSHOTS = (
    {'time': 0., 'drag': (0., 0.), 'scroll': 0.},
    {'time': 2.5, 'drag': (12., -3.), 'scroll': 2.},
    {'time': 5., 'drag': (-20., 9.), 'scroll': -1.},
    {'time': 9.9, 'drag': (0., 0.), 'scroll': 0.},
)


def reference_shader(dispersion, original=None):
    """Independent literal constant-wavelength wrapper; original AA main stays.

    No candidate transport(), camera-sample generator, or CAPTURE definition is
    used. Only shadeRay's three optical calls become one literal constant call,
    and output is taken immediately after the original AA average, before the
    vignette. Every other reachable archival function body remains intact.
    """
    constants = {-0.003: '-0.0030', 0.: '0.0', 0.005: '0.0050'}
    if dispersion not in constants:
        raise ValueError('Expected one archival wavelength dispersion')
    body = shaders.ARCHIVE.read_text(encoding='utf-8') if original is None else original
    # These lines are copied literally from the frozen archival shadeRay body.
    old = '''    vec3 r=opticalTransport(ro,rd,h,-0.0030);
    vec3 g=opticalTransport(ro,rd,h,0.0);
    vec3 b=opticalTransport(ro,rd,h,0.0050);
    return vec3(r.r,g.g,b.b);'''
    body = shaders.replace_once(body, old,
                               '    return opticalTransport(ro,rd,h,' + constants[dispersion] + ');')
    end_marker = '    color/=float(AA*AA);'
    if body.count(end_marker) != 1:
        raise ValueError('Expected one original AA average')
    body = body[:body.index(end_marker) + len(end_marker)] + '\n    fragColor=vec4(color,1.0);\n}\n'
    if body.count('#ifndef AA\n#define AA 2\n#endif') != 1:
        raise ValueError('Expected the original AA2 default')
    # Reject accidental external defines; never enable CAPTURE to obtain linear pixels.
    body = '#if defined(CAPTURE) || defined(AA)\n#error Reference requires archival AA2 and non-CAPTURE sampling\n#endif\n' + body
    body, functions = shaders.prune(body)
    for name in ('noise2', 'noise3'):
        body = re.sub(r'\b' + name + r'(?=\s*\()', 'cybr_scalar_' + name, body)
    return '''#version 330
uniform vec2 u_resolution,u_drag;
uniform float u_time,u_time_delta,u_scroll;
uniform int u_frame;
uniform vec4 u_mouse;
out vec4 fragColor;
''' + body, functions


def require_equivalence(finite, max_abs_error):
    if not finite or not math.isfinite(max_abs_error):
        raise AssertionError('Reference comparison contains non-finite values')
    if max_abs_error > MAX_ABSOLUTE_ERROR:
        raise AssertionError(f'Maximum absolute RGB error {max_abs_error:.10g} exceeds {MAX_ABSOLUTE_ERROR:.10g}')


def validate(width=128, height=72, event=None):
    # Imports here keep --help and reference-source unit tests GPU/dependency free.
    import moderngl
    import numpy as np
    from iris_native.renderer import create_context
    started = time.perf_counter()
    event = event or (lambda *args, **kwargs: None)
    original = shaders.ARCHIVE.read_text(encoding='utf-8')
    candidate_source, candidate_functions = shaders.transport(2, original)
    ctx, backend, attempts = create_context(moderngl.create_standalone_context)
    resources = []
    report = {
        'kind': 'native numerical validation, not browser Live', 'AA': 2,
        'width': width, 'height': height, 'snapshots': SNAPSHOTS,
        'backend': backend, 'failed_backend_attempts': attempts,
        'renderer': ctx.info.get('GL_RENDERER'), 'version': ctx.info.get('GL_VERSION'),
        'archive_normalized_text_sha256': hashlib.sha256(original.encode('utf-8')).hexdigest(),
        'candidate_normalized_text_sha256': hashlib.sha256(candidate_source.encode('utf-8')).hexdigest(),
        'hash_representation': 'UTF-8 text after universal-newline normalization (CRLF/CR to LF), re-encoded as UTF-8',
        'candidate_retained_functions': candidate_functions,
        'absolute_error_tolerance': MAX_ABSOLUTE_ERROR, 'process_limit_seconds': TIMEOUT_SECONDS,
        'reference_shaders': [], 'checks': [],
    }
    try:
        def program(name, source):
            start = time.perf_counter()
            event('compile-start', program=name, source_bytes=len(source.encode('utf-8')))
            value = ctx.program(vertex_shader=shaders.VERTEX, fragment_shader=source)
            resources.append(value)
            vao = ctx.vertex_array(value, []); resources.append(vao)
            event('compile-complete', program=name, compile_ms=(time.perf_counter()-start)*1000)
            return value, vao
        candidate, candidate_vao = program('split transport', candidate_source)
        accumulator, accumulator_vao = program('ordered float accumulation', shaders.accumulation())
        references = []
        for dispersion in shaders.DISPERSIONS:
            source, functions = reference_shader(dispersion, original)
            references.append(program(f'original AA2 wavelength {dispersion}', source))
            report['reference_shaders'].append({
                'dispersion': dispersion, 'normalized_text_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
                'source_bytes': len(source.encode('utf-8')), 'retained_functions': functions,
            })
        def target():
            texture = ctx.texture((width, height), 4, dtype='f4')
            texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
            texture.repeat_x = texture.repeat_y = False
            resources.append(texture)
            framebuffer = ctx.framebuffer(color_attachments=[texture]); resources.append(framebuffer)
            return texture, framebuffer
        sample, current_sum, scratch, reference_target = [target() for _ in range(4)]
        ctx.viewport = (0, 0, width, height); ctx.enable_only(0)
        accumulator['u_previousSum'].value = 0; accumulator['u_sample'].value = 1
        for shader in [candidate, *(value for value, _ in references)]:
            for name, value in {'u_resolution': (width, height), 'u_frame': 0,
                                'u_time_delta': 0., 'u_mouse': (0., 0., -1., -1.)}.items():
                if name in shader:
                    shader[name].value = value
        for snapshot, inputs in enumerate(SNAPSHOTS):
            for shader in [candidate, *(value for value, _ in references)]:
                shader['u_time'].value = inputs['time']
                shader['u_drag'].value = inputs['drag']
                shader['u_scroll'].value = inputs['scroll']
            for channel, dispersion in enumerate(shaders.DISPERSIONS):
                begin = time.perf_counter()
                current_sum[1].clear(0., 0., 0., 0.)
                candidate['u_dispersion'].value = dispersion
                for index in range(4):
                    candidate['u_sampleIndex'].value = index
                    sample[1].use(); candidate_vao.render(vertices=3)
                    scratch[1].use()
                    current_sum[0].use(location=0); sample[0].use(location=1)
                    accumulator_vao.render(vertices=3); ctx.finish()
                    current_sum, scratch = scratch, current_sum
                actual = np.frombuffer(current_sum[0].read(), dtype=np.float32).reshape(height, width, 4)[:, :, :3].copy()
                actual /= np.float32(4)
                reference_target[1].use(); references[channel][1].render(vertices=3); ctx.finish()
                expected = np.frombuffer(reference_target[0].read(), dtype=np.float32).reshape(height, width, 4)[:, :, :3].copy()
                finite = bool(np.isfinite(actual).all() and np.isfinite(expected).all())
                difference = np.abs(actual - expected) if finite else None
                maximum = float(difference.max()) if finite else None
                check = {'snapshot': snapshot, 'dispersion': dispersion, 'finite': finite,
                         'compared_rgb_components': actual.size, 'max_abs_error': maximum,
                         'different_components': int(np.count_nonzero(difference)) if finite else None,
                         'mean_abs_error': float(difference.mean()) if finite else None,
                         'draw_ms': (time.perf_counter()-begin)*1000}
                report['checks'].append(check); event('comparison', **check)
                require_equivalence(finite, maximum if maximum is not None else float('nan'))
        report.update(completed=True, passed=True,
                      compared_rgb_components=sum(item['compared_rgb_components'] for item in report['checks']),
                      max_abs_error=max(item['max_abs_error'] for item in report['checks']),
                      total_ms=(time.perf_counter()-started)*1000)
        return report
    finally:
        for resource in reversed(resources):
            resource.release()
        ctx.release()


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width', type=int, default=128, help='1-128 pixels; default 128')
    parser.add_argument('--height', type=int, default=72, help='1-72 pixels; default 72')
    parser.add_argument('--json', type=Path, default=Path('test-results/native-validation.json'))
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    options = parser.parse_args(arguments)
    if not (1 <= options.width <= 128 and 1 <= options.height <= 72):
        parser.error('Validation is bounded to width 1-128 and height 1-72')
    if options.json.exists():
        parser.error('Refusing to overwrite existing report: ' + str(options.json))
    def save(report):
        options.json.parent.mkdir(parents=True, exist_ok=True)
        with options.json.open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(report, handle, indent=2, allow_nan=False); handle.write('\n')
    if options.worker:
        started = time.perf_counter()
        def event(phase, **details):
            print(json.dumps(dict(phase=phase, elapsed_ms=(time.perf_counter()-started)*1000,
                                  **details), allow_nan=False), flush=True)
        try:
            report = validate(options.width, options.height, event)
            save(report); event('complete', **report)
            return 0
        except Exception as error:
            report = {'completed': False, 'passed': False, 'error_type': type(error).__name__, 'error': str(error)}
            if not options.json.exists():
                save(report)
            event('failed', **report)
            return 1
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), *arguments, '--worker'],
                                capture_output=True, text=True, encoding='utf-8', errors='replace',
                                timeout=TIMEOUT_SECONDS)
        sys.stdout.write(result.stdout); sys.stderr.write(result.stderr)
        return result.returncode
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ''
        if isinstance(output, bytes):
            output = output.decode('utf-8', errors='replace')
        sys.stdout.write(output)
        report = {'completed': False, 'passed': False, 'error_type': 'ProcessTimeout',
                  'timeout_seconds': TIMEOUT_SECONDS,
                  'error': 'Validation child stopped at its deadline; submitted driver work may take time to unwind.'}
        if not options.json.exists():
            save(report)
        print(json.dumps(dict(phase='timeout', **report)), flush=True)
        return 124


if __name__ == '__main__':
    raise SystemExit(main())
