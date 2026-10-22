"""Render an actual IRIS still with native OpenGL, in a bounded child process."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import time


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--width', type=int, default=160)
    result.add_argument('--height', type=int, default=90)
    result.add_argument('--time', type=float, default=0., help='Scene time in seconds')
    result.add_argument('--drag', type=float, nargs=2, default=(0., 0.), metavar=('X', 'Y'))
    result.add_argument('--scroll', type=float, default=0.)
    result.add_argument('--samples', type=int, choices=(1, 2), default=2,
                        help='AA dimension: 1 means one camera sample; 2 means four (default)')
    result.add_argument('--output', type=Path, default=Path('test-results/iris-native.png'))
    result.add_argument('--json', type=Path, dest='report', help='Optional JSON result and timing report')
    result.add_argument('--linear-npy', type=Path, help='Optional top-down linear RGB float32 array before vignette')
    result.add_argument('--timeout', type=float, default=45., help='Total child-process limit, seconds (1–300)')
    result.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    return result


def validate(options):
    if not (1 <= options.width <= 8192 and 1 <= options.height <= 8192):
        raise ValueError('Width and height must be between 1 and 8192; no automatic size reduction is used')
    if options.width * options.height * 16 * 6 > 512 * 1024 * 1024:
        raise ValueError('Selected resolution exceeds the 512 MiB render-target budget')
    if not all(math.isfinite(value) for value in (options.time, *options.drag, options.scroll, options.timeout)):
        raise ValueError('Time, drag, scroll and timeout must be finite')
    if not 1 <= options.timeout <= 300:
        raise ValueError('Timeout must be between 1 and 300 seconds')
    if options.output.suffix.lower() != '.png':
        raise ValueError('Output must have a .png extension')
    paths = [path.resolve() for path in (options.output, options.report, options.linear_npy) if path is not None]
    if len(set(paths)) != len(paths):
        raise ValueError('PNG, JSON and NPY outputs must have different paths')
    for path in paths:
        if path.exists():
            raise ValueError('Refusing to overwrite existing output: ' + str(path))


def write_report(path, report):
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
            handle.write('\n')


def worker(options):
    start = time.perf_counter()
    def event(phase, **details):
        print(json.dumps(dict(phase=phase, elapsed_ms=(time.perf_counter()-start)*1000,
                              **details), allow_nan=False), flush=True)
    try:
        # --help, validation and the supervisor need only Python's standard library.
        from iris_native.renderer import render
        display, linear, report = render(options.width, options.height, options.time,
                                         options.drag, options.scroll, options.samples, event)
        import numpy as np
        from PIL import Image
        options.output.parent.mkdir(parents=True, exist_ok=True)
        with options.output.open('xb') as handle:
            Image.fromarray(np.clip(display[:, :, :3] * 255, 0, 255).astype('uint8')).save(handle, format='PNG')
        if options.linear_npy is not None:
            options.linear_npy.parent.mkdir(parents=True, exist_ok=True)
            with options.linear_npy.open('xb') as handle:
                np.save(handle, linear, allow_pickle=False)
        report['output_png'] = options.output.name
        report['linear_npy'] = options.linear_npy.name if options.linear_npy is not None else None
        write_report(options.report, report)
        event('complete', **report)
        return 0
    except Exception as error:
        report = {'completed': False, 'error_type': type(error).__name__, 'error': str(error),
                  'renderer_kind': 'native OpenGL, not browser Live'}
        if options.report is not None and not options.report.exists():
            write_report(options.report, report)
        event('failed', **report)
        return 1


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    command = parser()
    options = command.parse_args(arguments)
    try:
        validate(options)
    except ValueError as error:
        command.error(str(error))
    if options.worker:
        return worker(options)
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), *arguments, '--worker'],
                                capture_output=True, text=True, encoding='utf-8', errors='replace',
                                timeout=options.timeout)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode
    except subprocess.TimeoutExpired as error:
        # subprocess.run kills and waits only for our child; no global GPU/browser kill.
        output = error.stdout or ''
        if isinstance(output, bytes):
            output = output.decode('utf-8', errors='replace')
        sys.stdout.write(output)
        report = {'completed': False, 'error_type': 'ProcessTimeout', 'timeout_seconds': options.timeout,
                  'error': 'Native renderer exceeded its process deadline; submitted driver work may take time to unwind.',
                  'renderer_kind': 'native OpenGL, not browser Live'}
        if options.report is not None and not options.report.exists():
            write_report(options.report, report)
        print(json.dumps(dict(phase='timeout', **report)), flush=True)
        return 124


if __name__ == '__main__':
    raise SystemExit(main())
