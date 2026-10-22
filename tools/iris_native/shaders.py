"""Derive smaller programs from the unchanged archival IRIS shader.

Each transport draw evaluates one original camera sample at one dispersion.
It retains full RGB transport weights and their original termination rule.
The renderer adds samples in x-fast/y-slow order, starting from zero, before
selecting each wavelength's component and dividing by AA*AA exactly once.
This changes program structure, not the scene or its sampling equations.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / 'IRIS-09.glsl'
DISPERSIONS = (-0.003, 0.0, 0.005)
VERTEX = '''#version 330
void main(){vec2 p=vec2(float((gl_VertexID<<1)&2),float(gl_VertexID&2));gl_Position=vec4(p*2.-1.,0.,1.);}
'''
FUNCTION = re.compile(r'(?m)^(?:float|vec[234]|mat[234]|bool|int|void|Hit|Light|Material)\s+(\w+)\s*\([^;{}]*\)\s*\{')
UNIFORMS = '''uniform vec2 u_resolution,u_drag;
uniform float u_time,u_time_delta,u_scroll,u_dispersion;
uniform int u_frame,u_sampleIndex;
uniform vec4 u_mouse;
out vec4 fragColor;
'''


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Archival shader structure changed: expected one ' + repr(old[:90]))
    return text.replace(old, new, 1)


def function_regions(source):
    """Locate current archival function definitions without rewriting bodies."""
    regions = []
    for match in FUNCTION.finditer(source):
        end, depth = match.end(), 1
        while depth:
            if end >= len(source):
                raise ValueError('Unclosed GLSL function: ' + match[1])
            depth += (source[end] == '{') - (source[end] == '}')
            end += 1
        regions.append((match[1], match.start(), end, source[match.start():end]))
    return regions


def prune(source, roots=('main',)):
    """Remove unreachable complete definitions; retained bodies stay unchanged."""
    functions = function_regions(source)
    wanted = set(roots)
    while True:
        enlarged = set(wanted)
        for name, _, _, body in functions:
            if name in wanted:
                enlarged.update(re.findall(r'\b(\w+)\s*\(', body))
        if enlarged == wanted:
            break
        wanted = enlarged
    for name, start, end, _ in reversed(functions):
        if name not in wanted:
            source = source[:start] + source[end:]
    return source, sorted({name for name, *_ in functions if name in wanted})


def _samples(samples):
    if type(samples) is not int or samples not in (1, 2):
        raise ValueError('samples must be 1 or 2 (AA dimension, giving 1 or 4 camera samples)')
    return samples


def _original(original):
    return ARCHIVE.read_text(encoding='utf-8') if original is None else original


def _namespace(source):
    # Desktop GLSL reserves these names as built-ins; only identifiers change.
    for name in ('noise2', 'noise3'):
        source = re.sub(r'\b' + name + r'(?=\s*\()', 'cybr_scalar_' + name, source)
    return source


def _sampling(source, samples):
    return replace_once(source, '#ifndef AA\n#define AA 2\n#endif',
                        '#define AA ' + str(_samples(samples)) + '''
#ifdef CAPTURE
#error Native split requires the original non-CAPTURE sampling
#endif''')


def transport(samples=2, original=None):
    """Return a GLSL330 single-sample/full-RGB program and its retained names."""
    body = _sampling(_original(original), samples)
    wrapper = '''vec3 wavelengthRay(vec3 ro,vec3 rd) {
    Hit h=sceneHit(ro,rd);
    if(h.id<0.5) return environment(ro,rd,0.25);
    if(h.id<19.5) return opaqueShade(h,ro,rd);
    return opticalTransport(ro,rd,h,u_dispersion);
}
'''
    body = replace_once(body, 'void main() {', wrapper + 'void main() {')
    body = replace_once(body, '    vec3 color=vec3(0);', '    vec3 color;')
    body = replace_once(body,
                        '    for(int y=0;y<AA;y++) {\n      for(int x=0;x<AA;x++) {',
                        '    int y=u_sampleIndex/AA;\n    int x=u_sampleIndex%AA;')
    body = replace_once(body,
                        '        color+=shadeRay(ro,rd);\n      }\n    }\n'
                        '    color/=float(AA*AA);',
                        '        color=wavelengthRay(ro,rd);')
    ending = '        color=wavelengthRay(ro,rd);'
    if body.count(ending) != 1:
        raise ValueError('Expected one camera output')
    body = body[:body.index(ending) + len(ending)] + '\n    fragColor=vec4(color,1.0);\n}\n'
    body, names = prune(body)
    return '#version 330\n' + UNIFORMS + _namespace(body), names


def accumulation():
    """Write into a distinct RGBA32F target; no blending or in-place feedback."""
    return '''#version 330
uniform sampler2D u_previousSum,u_sample;
out vec4 fragColor;
void main() {
    ivec2 pixel=ivec2(gl_FragCoord.xy);
    fragColor=texelFetch(u_previousSum,pixel,0)+texelFetch(u_sample,pixel,0);
}
'''


def composition(samples=2, original=None):
    """Select linear components, average once, then apply archival postprocess."""
    original = _original(original)
    if original.count('void main() {') != 1:
        raise ValueError('Expected one archival main function')
    main = original.index('void main() {')
    tail = original[main:]
    post_start = tail.index('    vec2 st=')
    capture_start = tail.index('#ifdef CAPTURE', post_start)
    display_start = tail.index('#else', capture_start) + len('#else')
    display_end = tail.index('#endif', display_start)
    post = tail[post_start:capture_start] + tail[display_start:display_end]
    if 'color*=0.96' not in post or 'fragColor=vec4(sat(color),1.0);' not in post:
        raise ValueError('Archival display postprocess changed')
    body = _sampling(original[:main], samples) + '''void main() {
    ivec2 pixel=ivec2(gl_FragCoord.xy);
    vec3 color=vec3(texelFetch(u_red,pixel,0).r,texelFetch(u_green,pixel,0).g,texelFetch(u_blue,pixel,0).b);
    color/=float(AA*AA);
''' + post + '\n}\n'
    body, _ = prune(body)
    return '''#version 330
uniform vec2 u_resolution;
uniform sampler2D u_red,u_green,u_blue;
out vec4 fragColor;
''' + body
