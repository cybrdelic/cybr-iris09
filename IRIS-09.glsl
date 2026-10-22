/*
  I R I S  /  0 9
  Revision 3. An exposed precision optical macro study, made for CYBRDELIC.
  FragCoord / GLSL ES 3.00 / one fragment pass / no external assets.

  Two recessed refractive elements, nine thin swept iris leaves,
  a linked actuator, milled grip geometry, anisotropic GGX, finite emitters,
  filtered machining, vector engraving, and a thin-lens camera.
  RGB dispersion is a three-wavelength approximation. Indirect light and
  secondary optical reflections are deliberately bounded approximations.
  The standalone capture uses this same source and averages linear samples.

  Aperture, actuator and camera repeat in a ten-second cycle.
  Drag horizontally to orbit; drag vertically to change the viewing height.
  Change AA to 1 on a slower device, or 3 for nine camera samples per pixel.
*/
#ifndef AA
#define AA 2
#endif
#define PI 3.141592653589793
#define TAU 6.283185307179586
#define EPS 0.00035
#define FAR 40.0

float pixelFootprint;
float sceneTime;
int lightPhase;

float sat(float x) { return clamp(x, 0.0, 1.0); }
vec3 sat(vec3 x) { return clamp(x, 0.0, 1.0); }
float sq(float x) { return x*x; }
mat2 rot(float a) { float c=cos(a),s=sin(a); return mat2(c,-s,s,c); }

float hash12(vec2 p) {
    vec3 q=fract(vec3(p.xyx)*vec3(0.1031,0.1030,0.0973));
    q+=dot(q,q.yzx+33.33);
    return fract((q.x+q.y)*q.z);
}
vec2 hash22(vec2 p) {
    vec3 q=fract(vec3(p.xyx)*vec3(0.1031,0.1030,0.0973));
    q+=dot(q,q.yzx+33.33);
    return fract((q.xx+q.yz)*q.zy);
}
float noise2(vec2 p) {
    vec2 i=floor(p),f=fract(p); f=f*f*(3.0-2.0*f);
    return mix(mix(hash12(i),hash12(i+vec2(1,0)),f.x),
               mix(hash12(i+vec2(0,1)),hash12(i+vec2(1,1)),f.x),f.y);
}
float noise3(vec3 p) {
    vec3 i=floor(p),f=fract(p); f=f*f*(3.0-2.0*f);
    vec2 q=i.xy+vec2(37,113)*i.z;
    return mix(mix(mix(hash12(q),hash12(q+vec2(1,0)),f.x),
                   mix(hash12(q+vec2(0,1)),hash12(q+vec2(1,1)),f.x),f.y),
               mix(mix(hash12(q+vec2(37,113)),hash12(q+vec2(38,113)),f.x),
                   mix(hash12(q+vec2(37,114)),hash12(q+vec2(38,114)),f.x),f.y),f.z);
}
float sdRoundBox2(vec2 p,vec2 b,float radius) {
    vec2 d=abs(p)-b+radius;
    return min(max(d.x,d.y),0.0)+length(max(d,0.0))-radius;
}
float sdBox(vec3 p,vec3 b) {
    vec3 d=abs(p)-b;
    return min(max(d.x,max(d.y,d.z)),0.0)+length(max(d,0.0));
}
float sdRoundBox3(vec3 p,vec3 b,float radius) {
    vec3 d=abs(p)-b+radius;
    return min(max(d.x,max(d.y,d.z)),0.0)+length(max(d,0.0))-radius;
}
float actuatorAngle() { return -.38+.54*(1.0-cos(sceneTime*PI/10.0)); }
vec2 nearer(vec2 a,vec2 b) { return a.x<b.x?a:b; }
vec2 sphereRoots(vec3 ro,vec3 rd,vec3 c,float radius) {
    vec3 v=ro-c; float b=dot(v,rd),h=b*b-dot(v,v)+radius*radius;
    if(h<0.0) return vec2(FAR);
    h=sqrt(h); return vec2(-b-h,-b+h);
}

// Only manufacturing-scale geometry belongs in the distance function.
// Surface grain, tool marks and inscriptions are evaluated after a hit.
vec2 bodyMap(vec3 p) {
    float r=length(p.xz),a=atan(p.z,p.x);
    vec2 q=vec2(r,p.y);
    vec2 d=vec2(sdRoundBox2(q-vec2(1.298,0.255),vec2(0.212,0.255),0.038),1.0);
    d=nearer(d,vec2(sdRoundBox2(q-vec2(1.303,0.513),vec2(0.220,0.031),0.006),2.0));
    d=nearer(d,vec2(sdRoundBox2(q-vec2(1.054,0.472),vec2(0.037,0.060),0.014),3.0));
    d=nearer(d,vec2(sdRoundBox2(q-vec2(1.500,0.102),vec2(0.036,0.046),0.013),2.0));
    d=nearer(d,vec2(sdRoundBox2(q-vec2(1.475,0.385),vec2(0.048,0.043),0.016),1.0));
    d=nearer(d,vec2(sdRoundBox2(q-vec2(1.485,0.224),vec2(0.031,0.018),0.007),1.0));
    d=nearer(d,vec2(sdRoundBox2(q-vec2(1.019,0.275),vec2(0.025,0.161),0.008),5.0));
    // Deep objective barrel: real annular steps and a recessed floor.
    d=nearer(d,vec2(sdRoundBox2(q-vec2(0.530,-0.077),vec2(0.555,0.023),0.010),5.0));
    d=nearer(d,vec2(sdRoundBox2(q-vec2(0.637,0.084),vec2(0.065,0.139),0.008),5.0));
    d=nearer(d,vec2(sdRoundBox2(q-vec2(0.548,0.211),vec2(0.026,0.015),0.004),5.0));
    d=nearer(d,vec2(sdRoundBox2(q-vec2(0.572,0.054),vec2(0.018,0.013),0.004),5.0));
    d=nearer(d,vec2(sdRoundBox2(q-vec2(0.501,0.026),vec2(0.018,0.008),0.003),5.0));
    d=nearer(d,vec2(sdRoundBox2(q-vec2(0.457,0.003),vec2(0.018,0.008),0.003),5.0));
    d=nearer(d,vec2(sdRoundBox2(q-vec2(0.408,-0.022),vec2(0.018,0.013),0.003),5.0));

    // Actual milled flutes on the side grip, kept out of the microscopic
    // material pattern. The corners catch raking light and alter silhouette.
    if(r>1.445 && p.y>.13 && p.y<.365) {
        float sector=TAU/120.0;
        float ga=floor((a+.5*sector)/sector)*sector;
        vec2 g=rot(ga)*p.xz-vec2(1.513,0.0);
        float flute=sdRoundBox3(vec3(g.x,p.y-.248,g.y),vec3(.025,.095,.012),.005);
        d.x=max(d.x,-flute);
    }
    // A fine annular assembly joint in the removable front plate.
    float seam=sdRoundBox2(vec2(r-1.462,p.y-.546),vec2(.0018,.007),.0010);
    d.x=max(d.x,-seam);
    // Two spanner recesses in the brass retaining ring.
    vec2 notch=rot(.31)*p.xz;
    float notchCut=sdRoundBox3(vec3(abs(notch.x)-1.054,p.y-.529,notch.y),
                              vec3(.041,.015,.018),.002);
    d.x=max(d.x,-notchCut);
    // The actuator travels in a real curved slot. The lever is added after
    // the cut, so it passes cleanly above the stationary scale plate.
    float slotAngle=atan(sin(a-.16),cos(a-.16));
    float ca=.16+clamp(slotAngle,-.61,.61);
    float track2=length(p.xz-1.439*vec2(cos(ca),sin(ca)))-.014;
    float track=max(track2,abs(p.y-.538)-.028);
    d.x=max(d.x,-track);

    // Three machined mounting ears, with real through-holes.
    float sector=TAU/3.0;
    float ea=floor((a+0.5*sector)/sector)*sector;
    vec2 e=rot(ea)*p.xz;
    float ear=sdRoundBox2(vec2(length(e-vec2(1.40,0.0)),p.y+0.012),vec2(0.322,0.079),0.042);
    float bore=length(e-vec2(1.57,0.0))-0.076;
    ear=max(ear,-bore);
    d=nearer(d,vec2(ear,1.0));

    // Six captive, slotted titanium screws on the face ring.
    float sa=floor((a+PI/6.0)/(PI/3.0))*(PI/3.0);
    vec2 s=rot(sa)*p.xz-vec2(1.348,0.0);
    float sr=length(s);
    float recess=sdRoundBox2(vec2(sr,p.y-0.550),vec2(0.062,0.028),0.006);
    d.x=max(d.x,-recess);
    float screw=sdRoundBox2(vec2(sr,p.y-0.529),vec2(0.058,0.014),0.007);
    vec2 sl=rot(0.48+sa*1.7)*s;
    float slot=sdBox(vec3(sl.x,p.y-0.544,sl.y),vec3(0.056,0.014,0.008));
    screw=max(screw,-slot);
    d=nearer(d,vec2(screw,4.0));
    // Stainless actuator with a knurled thumb knob and a captive pivot.
    vec2 lever=rot(actuatorAngle())*p.xz;
    float arm=sdRoundBox3(vec3(lever.x-1.526,p.y-.573,lever.y),vec3(.197,.015,.028),.011);
    d=nearer(d,vec2(arm,4.0));
    float pivot=sdRoundBox2(vec2(length(lever-vec2(1.439,0.0)),p.y-.556),vec2(.012,.041),.003);
    d=nearer(d,vec2(pivot,4.0));
    vec2 knob=lever-vec2(1.726,0.0);
    float ka=atan(knob.y,knob.x),kr=length(knob);
    float knobRadius=.066+.0025*cos(ka*28.0);
    float grip=sdRoundBox2(vec2(kr,p.y-.600),vec2(knobRadius,.044),.008);
    d=nearer(d,vec2(grip,1.0));
    float cap=sdRoundBox2(vec2(kr,p.y-.643),vec2(.049,.005),.003);
    d=nearer(d,vec2(cap,4.0));
    return d;
}
vec3 bodyNormal(vec3 p) {
    vec2 e=vec2(0.00045,0.0);
    return normalize(vec3(bodyMap(p+e.xyy).x-bodyMap(p-e.xyy).x,
                          bodyMap(p+e.yxy).x-bodyMap(p-e.yxy).x,
                          bodyMap(p+e.yyx).x-bodyMap(p-e.yyx).x));
}

struct Hit { float t; float id; vec3 n; vec2 uv; float bladeIndex; float edge; };
Hit missHit() { return Hit(FAR,0.0,vec3(0,1,0),vec2(0),0.0,0.0); }

// IRIS / 09 v3 -- nine thin spring-steel leaves with swept circular edges.
// Each leaf is the intersection of two circular prisms, an outer clip circle,
// and a thin canted slab. The blade roots continue under the retaining ring;
// no artificial polygon envelope interrupts the visible curved outline.
// Identical cant creates a cyclic over-under order without a tall wrap seam.
// Cant is 0.008 in local Z, vertical thickness 0.00065. Minimum sampled
// face-to-face clearance is 0.000297 across hinge angles 0..0.9 radians.
// Opening evolves over t=0..10, returning over t=10..20.

const float IRIS_PI = 3.14159265358979323846;
const float IRIS_RADIUS = 0.99;
const float IRIS_HINGE_RADIUS = 0.86;
const float IRIS_BLADE_THICKNESS = 0.00065;
const float IRIS_BLADE_CANT = 0.008;
const float IRIS_BLADE_HEIGHT = 0.260;
const vec3 IRIS_FRONT_ARC = vec3(0.69, 0.17, 1.15);
const vec3 IRIS_TRAILING_ARC = vec3(0.25, 1.20, 1.60);

float irisHingeAngle(float time)
{
    return 0.45 + 0.45 * cos(time * (IRIS_PI / 10.0));
}

float irisApertureApothem(float time)
{
    float a = irisHingeAngle(time);
    vec2 arc = vec2(cos(a)*IRIS_FRONT_ARC.x - sin(a)*IRIS_FRONT_ARC.y,
                    sin(a)*IRIS_FRONT_ARC.x + cos(a)*IRIS_FRONT_ARC.y);
    return length(vec2(IRIS_HINGE_RADIUS,0.0) + arc) - IRIS_FRONT_ARC.z;
}

// Clip a ray interval against dot(planeNormal, point) <= planeOffset.
// The supplied plane normal is unit length and points out of the solid.
bool irisClipPlane(
    vec3 ro, vec3 rd, vec3 planeNormal, float planeOffset,
    inout float tEnter, inout float tExit,
    inout vec3 enterNormal, inout vec3 exitNormal)
{
    float denominator = dot(planeNormal, rd);
    float distanceToPlane = planeOffset - dot(planeNormal, ro);
    if (abs(denominator) < 1.0e-8)
        return distanceToPlane >= -1.0e-7;

    float t = distanceToPlane / denominator;
    if (denominator < 0.0)
    {
        if (t > tEnter)
        {
            tEnter = t;
            enterNormal = planeNormal;
        }
    }
    else
    {
        if (t < tExit)
        {
            tExit = t;
            exitNormal = planeNormal;
        }
    }
    return tEnter <= tExit;
}

// Cylinder interval used by every blade.  The cylinder is centered on world Y.
bool irisClipCircle(
    vec3 ro, vec3 rd,
    out float tEnter, out float tExit,
    out vec3 enterNormal, out vec3 exitNormal)
{
    tEnter = -1.0e20;
    tExit = 1.0e20;
    enterNormal = vec3(0.0);
    exitNormal = vec3(0.0);

    float a = dot(rd.xz, rd.xz);
    float b = dot(ro.xz, rd.xz);
    float c = dot(ro.xz, ro.xz) - IRIS_RADIUS * IRIS_RADIUS;
    if (a < 1.0e-12)
        return c <= 0.0;

    float discriminant = b * b - a * c;
    if (discriminant < 0.0)
        return false;

    float root = sqrt(max(discriminant, 0.0));
    tEnter = (-b - root) / a;
    tExit = (-b + root) / a;
    vec3 pe = ro + tEnter * rd;
    vec3 px = ro + tExit * rd;
    enterNormal = vec3(pe.x, 0.0, pe.z) / IRIS_RADIUS;
    exitNormal = vec3(px.x, 0.0, px.z) / IRIS_RADIUS;
    return tExit > 1.0e-5;
}

// Intersect an exactly circular blade boundary, extruded vertically.
// Two disk constraints create a curved front lip and a swept trailing edge.
bool irisClipArc(vec3 ro, vec3 rd, vec3 arc,
    inout float tEnter, inout float tExit,
    inout vec3 enterNormal, inout vec3 exitNormal)
{
    vec2 q = ro.xz - arc.xy;
    float a = dot(rd.xz, rd.xz);
    float b = dot(q, rd.xz);
    float c = dot(q,q) - arc.z*arc.z;
    if (a < 1.0e-12) return c <= 0.0;
    float discriminant = b*b-a*c;
    if (discriminant < 0.0) return false;
    float root = sqrt(max(0.0,discriminant));
    float te = (-b-root)/a, tx = (-b+root)/a;
    if (te > tEnter) {
        tEnter = te;
        vec2 normal = (q+te*rd.xz)/arc.z;
        enterNormal = vec3(normal.x,0.0,normal.y);
    }
    if (tx < tExit) {
        tExit = tx;
        vec2 normal = (q+tx*rd.xz)/arc.z;
        exitNormal = vec3(normal.x,0.0,normal.y);
    }
    return tEnter <= tExit;
}

vec2 irisBladeEdgeOutward(vec2 localPoint)
{
    float nearest = 10.0;
    vec2 normal = vec2(-1.0,0.0);
    vec2 front=localPoint-IRIS_FRONT_ARC.xy;
    float d=IRIS_FRONT_ARC.z-length(front);
    if(d<nearest) { nearest=d; normal=normalize(front); }
    vec2 trailing=localPoint-IRIS_TRAILING_ARC.xy;
    if(IRIS_TRAILING_ARC.z-length(trailing)<nearest) normal=normalize(trailing);
    return normal;
}

// Positive distance to the nearest geometric outline, on the blade's top face.
// This can drive a fine edge bevel, edge wear, and a narrow highlight.
float irisBladeEdgeDistance(vec2 localPoint, vec2 worldPoint)
{
    float d = IRIS_RADIUS - length(worldPoint);
    d = min(d, IRIS_FRONT_ARC.z-length(localPoint-IRIS_FRONT_ARC.xy));
    d = min(d, IRIS_TRAILING_ARC.z-length(localPoint-IRIS_TRAILING_ARC.xy));
    return max(d, 0.0);
}

// Required public interface.
//
// - ro/rd: world ray; rd need not be normalized, but t is in that parameterization.
// - tClosest: only decreased when a closer positive blade hit is found.
// - normal: geometric outward world normal, including sidewalls and undersides.
// - localUV: rotating blade-local XZ coordinates about its actual hinge.
// - bladeID: integer-valued 0..8 as a float; useful for restrained material shifts.
// - edgeDistance: distance to the blade outline in scene units; zero at sidewalls.
//
// On false, tClosest is unchanged.  The remaining outputs have benign defaults.
bool hitIris(
    vec3 ro, vec3 rd, float time, inout float tClosest,
    out vec3 normal, out vec2 localUV, out float bladeID,
    out float edgeDistance)
{
    normal = vec3(0.0, 1.0, 0.0);
    localUV = vec2(0.0);
    bladeID = -1.0;
    edgeDistance = 0.0;

    float circleEnter, circleExit;
    vec3 circleEnterNormal, circleExitNormal;
    if (!irisClipCircle(ro, rd, circleEnter, circleExit,
                        circleEnterNormal, circleExitNormal))
        return false;
    if (circleEnter >= tClosest)
        return false;

    // Common vertical bounds reject rays that miss the entire blade stack.
    // These bounds also keep secondary rays from doing unnecessary polygon work.
    float stackEnter = circleEnter;
    float stackExit = circleExit;
    vec3 stackEnterNormal = circleEnterNormal;
    vec3 stackExitNormal = circleExitNormal;
    if (!irisClipPlane(ro, rd, vec3(0.0, 1.0, 0.0), 0.2710,
                       stackEnter, stackExit, stackEnterNormal, stackExitNormal))
        return false;
    if (!irisClipPlane(ro, rd, vec3(0.0, -1.0, 0.0),
                       -0.2555,
                       stackEnter, stackExit, stackEnterNormal, stackExitNormal))
        return false;
    if (stackExit <= 1.0e-5 || stackEnter >= tClosest)
        return false;

    float hingeAngle = irisHingeAngle(time);
    bool hitAny = false;
    for (int blade = 0; blade < 9; ++blade)
    {
        float hingeAzimuth = float(blade) * (2.0 * IRIS_PI / 9.0);
        vec2 hinge = IRIS_HINGE_RADIUS *
                     vec2(cos(hingeAzimuth), sin(hingeAzimuth));
        float angle = hingeAzimuth + hingeAngle;
        vec2 localX = vec2(cos(angle), sin(angle));
        vec2 localZ = vec2(-localX.y, localX.x);

        vec2 offset = ro.xz - hinge;
        vec3 lr = vec3(dot(offset, localX), ro.y, dot(offset, localZ));
        vec3 ld = vec3(dot(rd.xz, localX), rd.y, dot(rd.xz, localZ));

        float tEnter = circleEnter;
        float tExit = circleExit;
        vec3 enterNormal = vec3(dot(circleEnterNormal.xz, localX),
                                0.0, dot(circleEnterNormal.xz, localZ));
        vec3 exitNormal = vec3(dot(circleExitNormal.xz, localX),
                               0.0, dot(circleExitNormal.xz, localZ));

        // Identically canted sheets make the overlap cyclic: every blade
        // passes above its clockwise neighbor in their actual overlap region.
        // There is no accumulated nine-layer height discontinuity at one seam.
        float invLength = inversesqrt(1.0+IRIS_BLADE_CANT*IRIS_BLADE_CANT);
        vec3 sheetNormal = vec3(0.0,1.0,-IRIS_BLADE_CANT)*invLength;
        if (!irisClipPlane(lr,ld,sheetNormal,IRIS_BLADE_HEIGHT*invLength,
                           tEnter,tExit,enterNormal,exitNormal)) continue;
        if (!irisClipPlane(lr,ld,-sheetNormal,
                           (-IRIS_BLADE_HEIGHT+IRIS_BLADE_THICKNESS)*invLength,
                           tEnter,tExit,enterNormal,exitNormal)) continue;
        if (!irisClipArc(lr,ld,IRIS_FRONT_ARC,
                        tEnter,tExit,enterNormal,exitNormal)) continue;
        if (!irisClipArc(lr,ld,IRIS_TRAILING_ARC,
                        tEnter,tExit,enterNormal,exitNormal)) continue;
        if (tExit <= 1.0e-5 || tEnter >= tClosest)
            continue;

        bool entering = tEnter > 1.0e-5;
        float t = entering ? tEnter : tExit;
        if (t <= 1.0e-5 || t >= tClosest)
            continue;

        vec3 ln = entering ? enterNormal : exitNormal;
        vec3 lp = lr + ld * t;
        vec3 wp = ro + rd * t;
        normal = normalize(vec3(
            ln.x * localX.x + ln.z * localZ.x,
            ln.y,
            ln.x * localX.y + ln.z * localZ.y));
        localUV = lp.xz;
        bladeID = float(blade);
        edgeDistance = irisBladeEdgeDistance(localUV, wp.xz);
        if (abs(ln.y) < 0.5)
            edgeDistance = 0.0;
        tClosest = t;
        hitAny = true;
    }
    return hitAny;
}


Hit opaqueHit(vec3 ro,vec3 rd) {
    Hit h=missHit();
    if(rd.y< -0.00001) {
        float t=(-0.094-ro.y)/rd.y;
        if(t>EPS) h=Hit(t,6.0,vec3(0,1,0),(ro+t*rd).xz,0.0,0.0);
    }
    vec2 br=sphereRoots(ro,rd,vec3(0,0.23,0),1.88);
    if(br.y>EPS && br.x<h.t) {
        float t=max(EPS,br.x);
        float end=min(br.y,h.t);
        for(int i=0;i<104;i++) {
            vec3 p=ro+t*rd;
            vec2 d=bodyMap(p);
            float eps=max(0.00022,t*0.000035);
            if(d.x<eps) {
                h=Hit(t,d.y,bodyNormal(p),p.xz,0.0,0.0); break;
            }
            t+=max(d.x*0.86,0.00012);
            if(t>end) break;
        }
        vec3 bn;vec2 buv;float bi,be;
        float bt=h.t;
        if(hitIris(ro,rd,sceneTime,bt,bn,buv,bi,be)) h=Hit(bt,8.0,bn,buv,bi,be);

        // Recessed optical-black sensor beneath the aperture, with a gold rim.
        if(abs(rd.y)>0.00001) {
            float st=(-0.045-ro.y)/rd.y;
            vec3 p=ro+st*rd;
            if(st>EPS && st<h.t && length(p.xz)<0.391)
                h=Hit(st,9.0,vec3(0,1,0),p.xz,0.0,0.0);
        }
    }
    return h;
}

// Closed plano-convex optical elements recessed below the iris.
void capIntersection(vec3 ro,vec3 rd,float radius,float base,float edge,float opticalID,inout Hit h) {
    vec3 center=vec3(0.0,base-sqrt(radius*radius-edge*edge),0.0);
    vec2 ts=sphereRoots(ro,rd,center,radius);
    for(int root=0;root<2;root++) {
        float t=root==0?ts.x:ts.y;
        vec3 p=ro+rd*t;
        if(t>EPS && t<h.t && p.y>base-0.00001 && dot(p.xz,p.xz)<edge*edge+0.00001)
            h=Hit(t,opticalID,normalize(p-center),p.xz,0.0,0.0);
    }
    if(abs(rd.y)>0.00001) {
        float t=(base-ro.y)/rd.y;
        vec3 p=ro+rd*t;
        if(t>EPS && t<h.t && dot(p.xz,p.xz)<edge*edge)
            h=Hit(t,opticalID,vec3(0,-1,0),p.xz,0.0,0.0);
    }
}
void lensIntersection(vec3 ro,vec3 rd,inout Hit h) {
    capIntersection(ro,rd,1.40,0.052,0.560,21.0,h);
    capIntersection(ro,rd,2.05,-0.025,0.390,22.0,h);
}
Hit sceneHit(vec3 ro,vec3 rd) {
    Hit h=opaqueHit(ro,rd);
    lensIntersection(ro,rd,h);
    return h;
}

// Photographic lighting: three world-space rectangular studio emitters.
struct Light { vec3 p; vec3 u; vec3 v; vec2 size; vec3 color; };
Light getLight(int i) {
    vec3 p;
    vec2 size;
    vec3 col;
    if(i==0) {
        // Broad warm-white key, offset to move its reflected center away
        // from the aperture and toward the left part of the optical window.
        p=vec3(-3.6,4.1,-3.1);
        size=vec2(1.45,2.15);
        col=vec3(3.4,3.3,3.15);
    } else if(i==1) {
        // A narrow near-axis strip catches the recessed objective surfaces.
        p=vec3(3.1,2.9,-2.4);
        size=vec2(0.36,1.45);
        col=vec3(3.0,3.15,3.4);
    } else {
        // Broad low-radiance fill. Its reflection should remain subordinate.
        p=vec3(.2,1.8,4.5);
        size=vec2(2.40,1.00);
        col=vec3(1.30,1.35,1.40);
    }
    vec3 n=normalize(vec3(0.0,0.20,0.0)-p);
    vec3 u=normalize(cross(vec3(0,1,0),n));
    vec3 v=cross(n,u);
    return Light(p,u,v,size,col);
}

vec3 studioBackground(vec3 rd) {
    float up=smoothstep(-0.25,0.90,rd.y);
    vec3 ambient=mix(vec3(0.010,0.0105,0.011),
                     vec3(0.036,0.038,0.042),up);
    // A directional dark field acts like a broad black studio flag; it
    // provides reflection contrast without painting contrast into the metal.
    float flag=pow(max(dot(rd,normalize(vec3(-0.92,0.12,0.36))),0.0),6.0);
    return ambient*(1.0-0.72*flag);
}

vec3 softboxRadiance(Light l,vec2 uv) {
    vec2 q=uv/l.size;
    float outline=sdRoundBox2(q,vec2(1.0),0.11);
    float edge=1.0-smoothstep(-0.08,0.0,outline);
    // A diffusion cloth has a broad smooth center-to-edge intensity falloff.
    // This variation must be shared by illumination and reflected appearance.
    float diffusion=0.55+0.45*exp(-1.65*dot(q,q));
    float longitudinal=0.95+0.05*q.y;
    return l.color*(edge*diffusion*longitudinal);
}

vec3 environment(vec3 ro,vec3 rd,float roughness) {
    vec3 radiance=studioBackground(rd);
    for(int i=0;i<3;i++) {
        Light l=getLight(i);
        vec3 ln=normalize(cross(l.u,l.v));
        float den=dot(rd,ln);
        if(den < -0.00001) {
            float t=dot(l.p-ro,ln)/den;
            if(t>0.0) {
                vec3 q=ro+rd*t-l.p;
                vec2 uv=vec2(dot(q,l.u),dot(q,l.v));
                // Approximate footprint for optical roughness only. Opaque
                // metals use the separate GGX area-light integral instead.
                float blur=max(0.001,t*roughness*roughness*0.85);
                vec2 expanded=l.size+vec2(blur);
                vec2 profileUV=uv*l.size/expanded;
                float energy=(l.size.x*l.size.y)/(expanded.x*expanded.y);
                radiance+=softboxRadiance(l,profileUV)*energy;
            }
        }
    }
    return radiance;
}

float ambientOcclusion(vec3 p,vec3 n) {
    float occ=0.0,w=1.0;
    for(int i=1;i<=4;i++) {
        float d=0.035*float(i*i);
        float s=bodyMap(p+n*d).x;
        occ+=max(d-s,0.0)*w;w*=0.52;
    }
    return clamp(1.0-occ*2.1,0.12,1.0);
}
float shadow(vec3 p,vec3 lightPos) {
    vec3 rd=normalize(lightPos-p);float stop=length(lightPos-p);
    vec2 bound=sphereRoots(p,rd,vec3(0,0.23,0),1.88);
    if(bound.y<0.0) return 1.0;
    float t=max(0.008,bound.x),end=min(stop,bound.y),res=1.0;
    for(int i=0;i<28;i++) {
        float d=bodyMap(p+rd*t).x;
        res=min(res,9.0*d/t);
        if(d<0.0005 || t>end) break;
        t+=clamp(d,0.012,0.21);
    }
    return clamp(res,0.025,1.0);
}
vec3 fresnelSchlick(vec3 f0,float NoV) { return f0+(1.0-f0)*pow(1.0-sat(NoV),5.0); }
float lineMask(float dist,float halfWidth) {
    float fw=max(pixelFootprint*0.6,0.00024);
    return 1.0-smoothstep(halfWidth-fw,halfWidth+fw,abs(dist));
}
float ringScale(vec3 p) {
    float r=length(p.xz),a=atan(p.z,p.x);
    float k=(a/TAU+0.5)*90.0;
    float dk=abs(fract(k+0.5)-0.5)*TAU*r/90.0;
    float major=1.0-step(0.5,mod(floor(k+0.5),5.0));
    float start=mix(1.210,1.170,major);
    float radial=smoothstep(start-0.002,start+0.002,r)*(1.0-smoothstep(1.265,1.270,r));
    float ticks=lineMask(dk,0.0017+major*0.0007)*radial;
    float register=lineMask(a-0.93,0.004)*smoothstep(1.405,1.414,r)*(1.0-smoothstep(1.451,1.458,r));
    return max(ticks,register);
}


// Continuous laser-engraved vector strokes, evaluated analytically.
float strokeSegment(vec2 p,vec2 a,vec2 b) {
    vec2 d=b-a;
    return length(p-a-d*clamp(dot(p-a,d)/dot(d,d),0.0,1.0));
}
float letterDistance(int id,vec2 p) {
    float d=10.0;
    if(id==0) {
        d=abs(sdRoundBox2(p-vec2(0.48,0.5),vec2(0.36,0.44),0.15));
        d=max(d,-max(0.62-p.x,abs(p.y-0.50)-0.25));
    } else if(id==1) {
        d=min(strokeSegment(p,vec2(.10,.94),vec2(.48,.51)),
              strokeSegment(p,vec2(.86,.94),vec2(.48,.51)));
        d=min(d,strokeSegment(p,vec2(.48,.51),vec2(.48,.06)));
    } else if(id==2 || id==3) {
        d=strokeSegment(p,vec2(.14,.06),vec2(.14,.94));
        d=min(d,strokeSegment(p,vec2(.14,.94),vec2(.59,.94)));
        d=min(d,strokeSegment(p,vec2(.59,.94),vec2(.80,.80)));
        d=min(d,strokeSegment(p,vec2(.80,.80),vec2(.80,.66)));
        d=min(d,strokeSegment(p,vec2(.80,.66),vec2(.59,.52)));
        d=min(d,strokeSegment(p,vec2(.59,.52),vec2(.14,.52)));
        if(id==3) d=min(d,strokeSegment(p,vec2(.46,.52),vec2(.84,.06)));
        else {
            d=min(d,strokeSegment(p,vec2(.59,.52),vec2(.83,.37)));
            d=min(d,strokeSegment(p,vec2(.83,.37),vec2(.83,.22)));
            d=min(d,strokeSegment(p,vec2(.83,.22),vec2(.59,.06)));
            d=min(d,strokeSegment(p,vec2(.59,.06),vec2(.14,.06)));
        }
    } else if(id==5) {
        d=abs(sdRoundBox2(p-vec2(.48,.5),vec2(.34,.44),.20));
    } else if(id==6) {
        d=abs(sdRoundBox2(p-vec2(.47,.70),vec2(.33,.24),.17));
        d=min(d,strokeSegment(p,vec2(.80,.69),vec2(.73,.20)));
        d=min(d,strokeSegment(p,vec2(.73,.20),vec2(.49,.06)));
        d=min(d,strokeSegment(p,vec2(.49,.06),vec2(.21,.06)));
    }
    return d;
}
float engravingText(vec3 p) {
    float r=length(p.xz),a=atan(p.z,p.x);
    vec2 uv=vec2((1.57-a)*1.36,1.347-r)/0.058+vec2(4.15,.5);
    int ch=int(floor(uv.x/1.20));
    if(ch<0 || ch>6 || uv.y<-.2 || uv.y>1.2) return 0.0;
    vec2 local=vec2(uv.x-float(ch)*1.20,uv.y);
    float fw=max(pixelFootprint/0.058*.7,.008);
    return 1.0-smoothstep(.050-fw,.050+fw,letterDistance(ch,local));
}

struct Material { vec3 base; vec3 f0; float rough; float metal; vec3 n; vec3 tangent; float aniso; };

// A sparse set of shallow handling scratches on the face. The first two
// components are the normal slope in the radial/tangential frame, the third
// is the resolved scratch coverage. Filtering conserves the line's coverage
// when the width falls below a pixel instead of growing a dark painted line.
vec3 faceHandlingMarks(float r,float a) {
    vec3 marks=vec3(0.0);
    for(int j=0;j<15;j++) {
        float jf=float(j);
        float rr=1.140+.345*hash12(vec2(jf,81.3));
        float aa=TAU*hash12(vec2(jf,71.4));
        vec2 q=vec2(r-rr,atan(sin(a-aa),cos(a-aa))*rr);
        float angle=.20+.76*hash12(vec2(jf,93.7));
        vec2 axis=normalize(vec2(cos(angle),sin(angle)));
        if(j<10) axis=normalize(vec2(.10*cos(jf*2.3),1.0));
        float halfLength=.014+.070*hash12(vec2(jf,31.9));
        vec2 nearest=q-axis*clamp(dot(q,axis),-halfLength,halfLength);
        float width=.00025+.00032*hash12(vec2(jf,64.8));
        float filtered=sqrt(width*width+sq(pixelFootprint*.42));
        float profile=exp(-dot(nearest,nearest)/(filtered*filtered));
        float coverage=profile*width/filtered;
        float depth=.000055+.000050*hash12(vec2(jf,9.1));
        marks.xy-=nearest*(2.0*depth/(filtered*filtered))*coverage;
        marks.z+=coverage;
    }
    marks.z=min(marks.z,1.0);
    return marks;
}

float faceStamp(vec3 p) { return max(ringScale(p),engravingText(p)); }

Material materialAt(Hit h,vec3 p) {
    vec3 n=h.n;
    float r=max(length(p.xz),.0001),a=atan(p.z,p.x);
    vec3 radial=vec3(p.x/r,0,p.z/r),tangent=vec3(-radial.z,0,radial.x);
    float grain=noise3(p*87.0);
    Material m=Material(vec3(.025),vec3(.04),.32,0.0,n,tangent,0.0);
    if(h.id<1.5) {
        // Satin black anodizing. Tiny edge burnishing exposes the underlying
        // alloy only on rounded shoulders and heavily handled grip ridges.
        float orangePeel=noise3(p*145.0);
        float handling=noise3(p*17.0);
        m.base=vec3(.014,.017,.020)*(.91+.18*grain);
        m.f0=vec3(.043);m.rough=.325+.040*(orangePeel-.5)+.025*(handling-.5);
        float shoulder=pow(sat(4.0*abs(n.y)*(1.0-abs(n.y))),4.0);
        float burnish=shoulder*.42*pow(sat((handling-.25)/.75),2.0);
        if(abs(n.y)<.7 && r>1.43 && p.y>.15 && p.y<.36) {
            float atten=exp(-sq(pixelFootprint*168.0/r)*.6);
            n=normalize(n+.025*cos(a*120.0)*tangent*atten);
            m.base*=.90+.10*sin(a*168.0);
            m.rough+=.020*sin(a*168.0);
            burnish+=.018*pow(.5+.5*sin(a*168.0),8.0)*handling;
        }
        m.f0=mix(m.f0,vec3(.50,.53,.56),burnish);
        m.metal=burnish;
        m.rough=mix(m.rough,.245,burnish);
    } else if(h.id<2.5) {
        // Turned alloy: circumferential tool-feed plus much finer polishing.
        // Reflectance remains coherent; the spatial changes are chiefly
        // roughness and surface slope, as on a real uncoated machined face.
        m.base=vec3(.40,.42,.44);m.f0=vec3(.54,.565,.59);m.metal=1.0;
        float polish=noise2(vec2(r*24.0,a*7.0));
        float residue=noise2(p.xz*5.2+vec2(3.8,17.1));
        m.rough=.285+.040*(polish-.5)+.045*(residue-.5);
        m.aniso=.71+.035*(polish-.5);
        float slope=.020*sin(r*TAU*94.0+.18*sin(a*3.0))*exp(-.22*sq(TAU*94.0*pixelFootprint));
        slope+=.013*sin(r*TAU*211.0+.28*noise2(p.xz*3.5))*exp(-.22*sq(TAU*211.0*pixelFootprint));
        slope+=.0025*sin(r*TAU*24.0+.09*sin(a*7.0))*exp(-.22*sq(TAU*24.0*pixelFootprint));
        vec3 marks=faceHandlingMarks(r,a);
        float face=smoothstep(.50,.94,n.y);
        // A localized handling film beside the control changes the sheen,
        // leaving the alloy color and the underlying tool feed intact.
        float da=atan(sin(a+.06),cos(a+.06));
        vec2 fq=vec2((r-1.34)/.085,da*r/.22);
        float film=exp(-1.5*dot(fq,fq))*(.65+.35*noise2(vec2(r*75.0,a*14.0)))*face;
        m.rough-=.055*film;m.aniso*=1.0-.30*film;
        n=normalize(n+face*(radial*(slope+marks.x)+tangent*marks.y));
        m.rough+=.065*marks.z*face;
        m.aniso*=1.0-.28*marks.z;

        // Ink-filled shallow engraving. The recess has its own sloping lip,
        // so it catches the studio source as the camera moves. This is a
        // filtered bump relief, not a claim of displaced silhouette geometry.
        float stamp=faceStamp(p)*face;
        float e=max(.00028,pixelFootprint*.48);
        vec2 grad=vec2(faceStamp(p+vec3(e,0,0))-faceStamp(p-vec3(e,0,0)),
                       faceStamp(p+vec3(0,0,e))-faceStamp(p-vec3(0,0,e)))/(2.0*e);
        n=normalize(n+vec3(grad.x,0,grad.y)*(.00045*face));
        m.f0=mix(m.f0,vec3(.047,.050,.054),stamp);
        m.rough=mix(m.rough,.51,stamp);m.aniso*=1.0-stamp;
    } else if(h.id<3.5) {
        // The brass retains a clean turned highlight, with a slightly duller
        // surface at its protected seats. No large decorative corrosion maps.
        float patina=noise2(vec2(a*5.0,r*43.0)+vec2(2.1,13.7));
        float sheltered=(1.0-smoothstep(.447,.505,p.y))*.16;
        float oxidation=.055+.12*patina+sheltered;
        m.base=vec3(.48,.27,.10);m.f0=mix(vec3(.83,.56,.27),vec3(.45,.31,.13),oxidation);m.metal=1.0;
        m.rough=.235+.065*oxidation+.024*(grain-.5);m.aniso=.43;
        float slope=.016*sin(r*TAU*160.0+.12*sin(a*5.0))*exp(-.22*sq(TAU*160.0*pixelFootprint));
        slope+=.004*sin(r*TAU*48.0)*exp(-.22*sq(TAU*48.0*pixelFootprint));
        n=normalize(n+radial*slope*n.y);
    } else if(h.id<4.5) {
        float sa=floor((a+PI/6.0)/(PI/3.0))*(PI/3.0);
        vec2 s=rot(sa)*p.xz-vec2(1.348,0.0);
        vec2 sl=rot(.48+sa*1.7)*s;
        float captiveHead=(1.0-smoothstep(.061,.069,length(s)))*smoothstep(.49,.51,p.y);
        float slotFloor=(1.0-smoothstep(.527,.537,p.y))*captiveHead;
        float machining=noise2(sl*vec2(430.0,42.0));
        m.base=vec3(.32,.34,.35);m.f0=vec3(.59,.615,.635);m.metal=1.0;
        m.rough=.235+.060*(machining-.5);m.aniso=.40;
        float ba=-sa-.48-sa*1.7;
        m.tangent=vec3(cos(ba),0,sin(ba));
        m.f0=mix(m.f0,vec3(.075,.073,.068),slotFloor*.75);
        m.rough=mix(m.rough,.48,slotFloor);
        float toolScuff=exp(-sq((sl.y-.013)/max(.0008,pixelFootprint*.45)))
                       *(1.0-smoothstep(.014,.047,abs(sl.x)));
        m.rough+=.085*toolScuff*captiveHead;
    } else if(h.id<5.5) {
        m.base=vec3(.005,.006,.007);m.f0=vec3(.032);m.rough=.46+.025*(grain-.5);
        if(abs(n.y)<.5) {
            float ripple=sin(p.y*TAU*90.0);
            float att=exp(-.22*sq(TAU*90.0*pixelFootprint));
            m.base*=.88+.12*ripple*att;
            n=normalize(n+vec3(0,.025*cos(p.y*TAU*90.0)*att,0));
        }
    } else if(h.id<6.5) {
        m.base=vec3(.034,.032,.029)*(.92+.12*noise2(p.xz*1.4));
        m.f0=vec3(.026);m.rough=.58;
        float e=.001;
        vec2 g=vec2(noise2((p.xz+vec2(e,0))*110.0)-noise2((p.xz-vec2(e,0))*110.0),
                    noise2((p.xz+vec2(0,e))*110.0)-noise2((p.xz-vec2(0,e))*110.0));
        n=normalize(n+vec3(g.x,0,g.y)*.018);
    } else if(h.id<8.5) {
        float pat=.5+(noise2(h.uv*vec2(170.0,4.0)+h.bladeIndex*8.0)-.5)
                    *exp(-2.0*sq(pixelFootprint*170.0));
        float batch=hash12(vec2(h.bladeIndex,23.1));
        m.base=vec3(.006,.007,.008);m.f0=vec3(.055,.059,.065);m.metal=.72;
        m.rough=.42+.010*(pat-.5)+.008*(batch-.5);m.aniso=.48;
        float ba=h.bladeIndex*TAU/9.0+irisHingeAngle(sceneTime);
        m.tangent=vec3(cos(ba),0,sin(ba));
        float striation=.003*sin(h.uv.y*TAU*225.0+batch*TAU)*exp(-.22*sq(TAU*225.0*pixelFootprint));
        n=normalize(n+vec3(-sin(ba),0,cos(ba))*striation);
        float bevel=1.0-smoothstep(.00008,.0005,h.edge);
        vec2 edgeOut=irisBladeEdgeOutward(h.uv);
        vec2 wo=mat2(cos(ba),sin(ba),-sin(ba),cos(ba))*edgeOut;
        if(n.y>.8) n=normalize(n+vec3(wo.x,0,wo.y)*bevel*.30);
        float edgeMetal=1.0-smoothstep(.00008,.00025,h.edge);
        m.f0=mix(m.f0,vec3(.29,.31,.34),edgeMetal*.30);
        m.rough=mix(m.rough,.235,bevel);
    } else {
        m.base=vec3(.002,.004,.006);m.f0=vec3(.006,.009,.012);m.rough=.32;
        float grid=lineMask(abs(fract(p.x*110.0+.5)-.5)/110.0,.00015)
                  *lineMask(abs(fract(p.z*110.0+.5)-.5)/110.0,.00015);
        m.base+=grid*vec3(.001,.002,.003);
    }
    m.n=n;
    return m;
}


// Anisotropic Trowbridge-Reitz microfacets with height-correlated Smith
// masking. Four 5x5 parity subgrids form a 10x10 Gauss-Legendre light rule.
// Camera samples interleave those subgrids; each finite source keeps its
// radiance and optical reflections on the identical diffuser profile.
vec2 gaussNode(int i) {
#if !defined(CAPTURE) && AA==1
    // The fast preview uses a complete lower-order rule rather than an
    // unbalanced single quarter of the high-quality light integral.
    int j=i/2;
    if(j==0) return vec2(-.9061798459,.2369268851);
    if(j==1) return vec2(-.5384693101,.4786286705);
    if(j==2) return vec2(0,.5688888889);
    if(j==3) return vec2(.5384693101,.4786286705);
    return vec2(.9061798459,.2369268851);
#else
    if(i==0) return vec2(-0.97390652852,0.06667134431);
    if(i==1) return vec2(-0.86506336669,0.14945134915);
    if(i==2) return vec2(-0.67940956830,0.21908636252);
    if(i==3) return vec2(-0.43339539413,0.26926671931);
    if(i==4) return vec2(-0.14887433898,0.29552422471);
    if(i==5) return vec2(0.14887433898,0.29552422471);
    if(i==6) return vec2(0.43339539413,0.26926671931);
    if(i==7) return vec2(0.67940956830,0.21908636252);
    if(i==8) return vec2(0.86506336669,0.14945134915);
    return vec2(0.97390652852,0.06667134431);
#endif
}
float ggxLambda(vec3 w,vec3 n,vec3 t,vec3 b,vec2 alpha) {
    float nz=max(abs(dot(w,n)),.0001);
    float slope=sq(alpha.x*dot(w,t))+sq(alpha.y*dot(w,b));
    return .5*(sqrt(1.0+slope/(nz*nz))-1.0);
}
vec3 microfacetBRDF(Material m,vec3 n,vec3 t,vec3 b,vec2 alpha,
                    vec3 V,vec3 L,float lambdaV) {
    float NoV=max(dot(n,V),.0001),NoL=dot(n,L);
    if(NoL<=0.0) return vec3(0);
    vec3 H=normalize(V+L);
    float hd=sq(dot(H,t)/alpha.x)+sq(dot(H,b)/alpha.y)+sq(dot(H,n));
    float D=1.0/(PI*alpha.x*alpha.y*hd*hd);
    float G=1.0/(1.0+lambdaV+ggxLambda(L,n,t,b,alpha));
    vec3 F=fresnelSchlick(m.f0,max(dot(V,H),0.0));
    vec3 spec=F*(D*G/max(4.0*NoV*NoL,.00001));
    vec3 diffuse=m.base*((1.0-m.metal)/PI)*(1.0-F);
    return diffuse+spec;
}
vec3 opaqueShade(Hit h,vec3 ro,vec3 rd) {
    vec3 p=ro+rd*h.t;
    Material m=materialAt(h,p);
    vec3 n=dot(m.n,rd)>0.0?-m.n:m.n;
    vec3 V=-rd;
    float NoV=max(dot(n,V),.0001);
    vec3 tangent=m.tangent-n*dot(n,m.tangent);
    if(dot(tangent,tangent)<.00001)
        tangent=abs(n.y)<.9?cross(n,vec3(0,1,0)):cross(n,vec3(1,0,0));
    tangent=normalize(tangent);
    vec3 bitangent=cross(n,tangent);
    float aspect=sqrt(max(.15,1.0-.88*m.aniso));
    vec2 alpha=max(vec2(.025),m.rough*m.rough*vec2(aspect,1.0/aspect));
    float lambdaV=ggxLambda(V,n,tangent,bitangent,alpha);
    float ao=ambientOcclusion(p+n*.0015,n);
    bool blade=h.id>7.5 && h.id<8.5;
    if(h.id>7.5 && h.id<9.5) ao*=.80;
    vec3 F=fresnelSchlick(m.f0,NoV);
    vec3 c=m.base*(1.0-m.metal)*(1.0-F)*(.037+.028*max(n.y,0.0))*ao;
    vec3 R=reflect(rd,n);
    c+=studioBackground(R)*F*mix(ao,1.0,pow(1.0-NoV,3.0));
    c+=m.f0*m.metal*(.012*m.rough)*ao;
    for(int i=0;i<3;i++) {
        Light l=getLight(i);
        vec3 ln=normalize(cross(l.u,l.v));
        float visibility=shadow(p+n*.0015,l.p);
        if(blade) {
            float cover=0.0;
            for(int j=0;j<3;j++) {
                vec3 lp=l.p+l.u*((float(j)-1.0)*l.size.x*.6);
                vec3 dd=lp-p;float limit=length(dd);dd/=limit;
                vec3 nn;vec2 uv;float bi,be;
                bool covered=hitIris(p+h.n*.00008,dd,sceneTime,limit,nn,uv,bi,be);
                cover+=covered?0.0:1.0;
            }
            visibility*=mix(.055,1.0,cover/3.0);
        }
        float lightWeight=4.0;
#if !defined(CAPTURE) && AA>1
        int count=(AA*AA+3-lightPhase)/4;
        lightWeight=float(AA*AA)/float(count);
#endif
#if !defined(CAPTURE) && AA==1
        lightWeight=1.0;
#endif
        vec3 integral=vec3(0);
        for(int sy=0;sy<5;sy++) {
            vec2 gy=gaussNode(sy*2+lightPhase/2);
            for(int sx=0;sx<5;sx++) {
                vec2 gx=gaussNode(sx*2+lightPhase%2);
                vec2 uv=vec2(gx.x,gy.x)*l.size;
                vec3 dl=l.p+l.u*uv.x+l.v*uv.y-p;
                float d2=dot(dl,dl);vec3 L=dl*inversesqrt(d2);
                float cosLight=max(-dot(ln,L),0.0),NoL=max(dot(n,L),0.0);
                float measure=lightWeight*gx.y*gy.y*l.size.x*l.size.y*cosLight*NoL/d2;
                integral+=softboxRadiance(l,uv)*microfacetBRDF(m,n,tangent,bitangent,alpha,V,L,lambdaV)*measure;
            }
        }
        c+=integral*visibility;
    }
    return c;
}

// Unpolarized thin-film reflectance evaluated at three visible wavelengths.
vec3 coatingFresnel(float ci,float substrateIOR,float thickness) {
    ci=clamp(ci,0.001,1.0);
    const float nf=1.28;
    float sf2=(1.0-ci*ci)/(nf*nf),cf=sqrt(max(0.0,1.0-sf2));
    float cs=sqrt(max(0.0,1.0-(1.0-ci*ci)/(substrateIOR*substrateIOR)));
    float r01s=(ci-nf*cf)/(ci+nf*cf),r12s=(nf*cf-substrateIOR*cs)/(nf*cf+substrateIOR*cs);
    float r01p=(nf*ci-cf)/(nf*ci+cf),r12p=(substrateIOR*cf-nf*cs)/(substrateIOR*cf+nf*cs);
    vec3 phase=4.0*PI*nf*thickness*cf/vec3(610.0,550.0,460.0);
    vec3 c=cos(phase);
    vec3 Rs=(r01s*r01s+r12s*r12s+2.0*r01s*r12s*c)/(1.0+sq(r01s*r12s)+2.0*r01s*r12s*c);
    vec3 Rp=(r01p*r01p+r12p*r12p+2.0*r01p*r12p*c)/(1.0+sq(r01p*r12p)+2.0*r01p*r12p*c);
    return sat((Rs+Rp)*0.5);
}
float dielectricFresnel(float ci,float etaI,float etaT) {
    float st2=sq(etaI/etaT)*(1.0-ci*ci);
    if(st2>=1.0) return 1.0;
    float ct=sqrt(max(0.0,1.0-st2));
    float rs=(etaI*ci-etaT*ct)/(etaI*ci+etaT*ct);
    float rp=(etaT*ci-etaI*ct)/(etaT*ci+etaI*ct);
    return 0.5*(rs*rs+rp*rp);
}
float opticalIOR(float opticalID,float dispersion) {
    if(opticalID>21.5) return 1.62+dispersion*1.25;
    return 1.58+dispersion*1.1;
}
vec3 opticalAbsorption(float opticalID) {
    return opticalID>21.5?vec3(.24,.055,.11):vec3(.12,.030,.055);
}
vec3 opticalFresnel(float opticalID,float ci,float ior,bool entering) {
    // Reciprocity: reverse incidence uses the corresponding external cosine.
    // Both air/glass surfaces are AR-coated.
    float airSin2=entering?(1.0-ci*ci):ior*ior*(1.0-ci*ci);
    if(airSin2>=1.0) return vec3(1.0);
    float airCos=sqrt(max(0.0,1.0-airSin2));
    float thickness=opticalID>21.5?146.0:133.0;
    return coatingFresnel(airCos,ior,thickness);
}
vec3 opticalTransport(vec3 ro,vec3 rd,Hit first,float dispersion) {
    vec3 sum=vec3(0),weight=vec3(1);Hit h=first;
    for(int bounce=0;bounce<24;bounce++) {
        if(h.id<0.5) { sum+=weight*environment(ro,rd,0.0);break; }
        if(h.id<19.5) { sum+=weight*opaqueShade(h,ro,rd);break; }
        vec3 p=ro+rd*h.t;
        bool entering=dot(rd,h.n)<0.0;
        vec3 N=entering?h.n:-h.n;
        float ior=opticalIOR(h.id,dispersion);
        float ei=entering?1.0:ior,et=entering?ior:1.0;
        if(!entering) weight*=exp(-opticalAbsorption(h.id)*h.t);
        float ci=max(dot(-rd,N),0.0001);
        vec3 F=opticalFresnel(h.id,ci,ior,entering);
        vec3 refracted=refract(rd,N,ei/et);
        vec3 reflected=reflect(rd,N);
        if(dot(refracted,refracted)<0.01) {
            ro=p+reflected*0.0007;rd=reflected;
        } else {
            vec3 reflectedLight=environment(p,reflected,0.018);
            if(h.id>20.5) {
                Hit rh=opaqueHit(p+reflected*0.0007,reflected);
                if(rh.id>0.5) reflectedLight=opaqueShade(rh,p+reflected*0.0007,reflected);
            }
            sum+=weight*F*reflectedLight;
            weight*=1.0-F;
            ro=p+refracted*0.0007;rd=refracted;
        }
        if(max(weight.r,max(weight.g,weight.b))<0.005) break;
        h=sceneHit(ro,rd);
    }
    return sum;
}
vec3 shadeRay(vec3 ro,vec3 rd) {
    Hit h=sceneHit(ro,rd);
    if(h.id<0.5) return environment(ro,rd,0.25);
    if(h.id<19.5) return opaqueShade(h,ro,rd);
    // Three close IOR values separate actual geometric refraction per channel.
    vec3 r=opticalTransport(ro,rd,h,-0.0030);
    vec3 g=opticalTransport(ro,rd,h,0.0);
    vec3 b=opticalTransport(ro,rd,h,0.0050);
    return vec3(r.r,g.g,b.b);
}

vec3 aces(vec3 x) { return sat((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14)); }

void main() {
    sceneTime=u_time*2.0;
    float az=0.52+0.13*sin(TAU*u_time/10.0+0.35)+u_drag.x/max(u_resolution.x,1.0)*2.5;
    float elev=0.690+clamp(u_drag.y/max(u_resolution.y,1.0),-0.2,0.25)*1.2;
    float distance=6.55*clamp(exp(-u_scroll*0.08),0.72,1.5);
    vec3 target=vec3(-0.015,0.235,0.0);
    vec3 camera=target+distance*vec3(sin(az)*cos(elev),sin(elev),cos(az)*cos(elev));
    vec3 forward=normalize(target-camera),right=normalize(cross(forward,vec3(0,1,0))),up=cross(right,forward);
    float focal=4.20;
    float focusDistance=distance-.035;
    pixelFootprint=2.0*distance/(focal*u_resolution.y);
    vec3 color=vec3(0);
    for(int y=0;y<AA;y++) {
      for(int x=0;x<AA;x++) {
        vec2 jitter;float seed;
#ifdef CAPTURE
        seed=float(u_frame);
        jitter=hash22(gl_FragCoord.xy+vec2(seed*137.15,seed*73.71))-0.5;
#else
        seed=float(x+y*AA);
        jitter=(vec2(float(x),float(y))+0.5)/float(AA)-0.5;
#endif
        lightPhase=int(seed)%4;
        vec2 uv=(2.0*(gl_FragCoord.xy+jitter)-u_resolution)/u_resolution.y;
        vec3 rd=normalize(forward*focal+right*uv.x+up*uv.y);
        vec3 focalPoint=camera+rd*(focusDistance/max(dot(rd,forward),0.01));
        vec2 disk=hash22(gl_FragCoord.xy+vec2(seed*41.71+6.3,seed*91.17+2.5));
        float angle=TAU*disk.y,radius=sqrt(disk.x)*0.034;
        vec3 ro=camera+right*(radius*cos(angle))+up*(radius*sin(angle));
        rd=normalize(focalPoint-ro);
        color+=shadeRay(ro,rd);
      }
    }
    color/=float(AA*AA);
    vec2 st=(2.0*gl_FragCoord.xy-u_resolution)/u_resolution.y;
    color*=0.96*(1.0-0.075*dot(st,st));
#ifdef CAPTURE
    fragColor=vec4(max(color,0.0),1.0);
#else
    color=pow(aces(max(color,0.0)),vec3(1.0/2.2));
    color+=(hash12(gl_FragCoord.xy)-0.5)/700.0;
    fragColor=vec4(sat(color),1.0);
#endif
}
