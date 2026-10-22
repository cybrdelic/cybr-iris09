"""Native OpenGL330 execution. Third-party imports and GPU work are explicit."""
import hashlib
import os
import platform
import time
from . import shaders


def context_candidates(system=None):
    system = system or platform.system()
    if system == 'Linux':
        return [('egl', {'backend': 'egl'}), ('default', {})]
    return [('wgl-default' if system == 'Windows' else 'cgl-default' if system == 'Darwin' else 'default', {})]


def create_context(factory, system=None, backend=None):
    selected = (backend or os.environ.get('CYBR_IRIS_GL_BACKEND', 'auto')).lower()
    if selected not in ('auto', 'mesa'):
        raise ValueError('CYBR_IRIS_GL_BACKEND must be auto or mesa')
    if selected == 'mesa':
        from .mesa_context import create_mesa_context
        return create_mesa_context(factory), 'mesa-egl-surfaceless', []
    attempts = []
    for name, options in context_candidates(system):
        try:
            context = factory(require=330, **options)
            return context, name, attempts
        except Exception as error:
            attempts.append({'backend': name, 'error': str(error)})
    raise RuntimeError('OpenGL 3.3 context unavailable: ' + '; '.join(
        item['backend'] + ': ' + item['error'] for item in attempts))


def render(width, height, time_value, drag, scroll, samples=2, event=None):
    """Return top-down display/linear float arrays and a JSON-compatible report.

    The outer CLI owns the process deadline. Every sample is completed before
    reusing its buffers, and no unrelated processes or contexts are terminated.
    """
    import moderngl
    import numpy as np
    begin = time.perf_counter()
    event = event or (lambda *args, **kwargs: None)
    archive = shaders.ARCHIVE.read_text(encoding='utf-8')
    source, names = shaders.transport(samples=samples, original=archive)
    ctx, backend, failed_backends = create_context(moderngl.create_standalone_context)
    resources = []
    report = {
        'renderer_kind': 'native OpenGL, not browser Live', 'platform': platform.system(),
        'backend': backend, 'failed_backend_attempts': failed_backends,
        'renderer': ctx.info.get('GL_RENDERER'), 'version': ctx.info.get('GL_VERSION'),
        'resolution': [width, height], 'time': time_value, 'drag': list(drag), 'scroll': scroll,
        'AA': samples, 'camera_samples': samples * samples, 'wavelengths': list(shaders.DISPERSIONS),
        'archive_normalized_text_sha256': hashlib.sha256(archive.encode('utf-8')).hexdigest(),
        'transport_shader_normalized_text_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
        'hash_representation': 'UTF-8 text after universal-newline normalization (CRLF/CR to LF), re-encoded as UTF-8',
        'transport_source_bytes': len(source.encode()), 'retained_functions': names,
    }
    try:
        maximum = ctx.info.get('GL_MAX_TEXTURE_SIZE', 0)
        if maximum and max(width, height) > maximum:
            raise ValueError(f'Selected resolution exceeds GPU texture limit {maximum}')
        # Six RGBA32F textures; fail rather than silently reduce selected size.
        allocation = width * height * 16 * 6
        if allocation > 512 * 1024 * 1024:
            raise ValueError('Selected resolution exceeds the 512 MiB render-target budget')
        report['render_target_bytes'] = allocation
        event('context-ready', backend=backend, renderer=report['renderer'])
        started = time.perf_counter()
        programs = []
        for name, fragment in [('transport', source), ('accumulation', shaders.accumulation()),
                               ('composition', shaders.composition(samples, archive))]:
            event('compile-start', program=name, source_bytes=len(fragment.encode()))
            program = ctx.program(vertex_shader=shaders.VERTEX, fragment_shader=fragment)
            programs.append(program); resources.append(program)
            event('compile-complete', program=name)
        report['compile_ms'] = (time.perf_counter() - started) * 1000
        transport, accumulator, composite = programs
        vaos = [ctx.vertex_array(program, []) for program in programs]
        resources.extend(vaos)

        def target():
            texture = ctx.texture((width, height), 4, dtype='f4')
            texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
            texture.repeat_x = texture.repeat_y = False
            resources.append(texture)
            framebuffer = ctx.framebuffer(color_attachments=[texture])
            resources.append(framebuffer)
            return texture, framebuffer

        sample = target(); sums = [target() for _ in range(3)]; scratch = target(); output = target()
        ctx.viewport = (0, 0, width, height); ctx.enable_only(0)
        for name, value in {'u_resolution': (width, height), 'u_time': time_value,
                            'u_drag': tuple(drag), 'u_scroll': scroll, 'u_frame': 0,
                            'u_time_delta': 0., 'u_mouse': (0., 0., -1., -1.)}.items():
            if name in transport:
                transport[name].value = value
        accumulator['u_previousSum'].value = 0; accumulator['u_sample'].value = 1
        composite['u_resolution'].value = (width, height)
        for unit, name in enumerate(('u_red', 'u_green', 'u_blue')):
            composite[name].value = unit
        report['wavelength_ms'] = []
        started = time.perf_counter()
        for channel, dispersion in enumerate(shaders.DISPERSIONS):
            channel_start = time.perf_counter()
            sums[channel][1].clear(0., 0., 0., 0.)
            transport['u_dispersion'].value = dispersion
            for index in range(samples * samples):
                transport['u_sampleIndex'].value = index
                sample[1].use(); vaos[0].render(vertices=3)
                scratch[1].use()
                # Bind after target allocation/activation: avoid stale unit bindings.
                sums[channel][0].use(location=0); sample[0].use(location=1)
                vaos[1].render(vertices=3); ctx.finish()
                sums[channel], scratch = scratch, sums[channel]
                event('sample-complete', wavelength=channel, sample=index)
            report['wavelength_ms'].append((time.perf_counter() - channel_start) * 1000)
        linear = np.empty((height, width, 3), dtype=np.float32)
        for channel in range(3):
            pixels = np.frombuffer(sums[channel][0].read(), dtype=np.float32).reshape(height, width, 4)
            if not np.isfinite(pixels).all():
                raise RuntimeError('Non-finite transport output')
            linear[:, :, channel] = pixels[:, :, channel] / np.float32(samples * samples)
        output[1].use()
        for unit in range(3):
            sums[unit][0].use(location=unit)
        vaos[2].render(vertices=3); ctx.finish()
        display = np.frombuffer(output[0].read(), dtype=np.float32).reshape(height, width, 4).copy()
        if not np.isfinite(display).all():
            raise RuntimeError('Non-finite composed output')
        report.update(render_ms=(time.perf_counter() - started) * 1000,
                      total_ms=(time.perf_counter() - begin) * 1000,
                      finite=True, completed=True, linear_range=[float(linear.min()), float(linear.max())],
                      display_range=[float(display.min()), float(display.max())])
        return display[::-1].copy(), linear[::-1].copy(), report
    finally:
        for resource in reversed(resources):
            resource.release()
        ctx.release()
