'use strict';
// This worker owns all WebGL calls. The UI never waits synchronously for a GPU.
let gl, surface, program, vao, uniforms;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function waitForGPU() {
  const fence = gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE, 0);
  gl.flush();
  const start = performance.now();
  try {
    for (;;) {
      const result = gl.clientWaitSync(fence, 0, 0);
      if (result === gl.ALREADY_SIGNALED || result === gl.CONDITION_SATISFIED) return;
      if (result === gl.WAIT_FAILED || gl.isContextLost()) throw Error('Graphics context interrupted');
      if (performance.now() - start > 10000) throw Error('GPU tile exceeded the 10 second budget');
      await delay(8);
    }
  } finally { gl.deleteSync(fence); }
}
function probe() {
  surface = new OffscreenCanvas(1, 1);
  gl = surface.getContext('webgl2', {alpha:false, antialias:false, preserveDrawingBuffer:true});
  if (!gl) throw Error('Worker WebGL2 is unavailable in this browser');
  surface.addEventListener('webglcontextlost', event => {
    event.preventDefault(); postMessage({type:'error', message:'Graphics context interrupted. Select Live to retry.'});
  });
  const debug = gl.getExtension('WEBGL_debug_renderer_info');
  postMessage({type:'capabilities',renderer:debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),version:gl.getParameter(gl.VERSION)});
}
async function initialize(message) {
  if (!gl) throw Error('WebGL preflight must complete before compiling');
  const extension = gl.getExtension('KHR_parallel_shader_compile');
  const shaders = [[gl.VERTEX_SHADER, message.vertex], [gl.FRAGMENT_SHADER, message.fragment]].map(([type, source]) => {
    const shader = gl.createShader(type); gl.shaderSource(shader, source); gl.compileShader(shader); return shader;
  });
  program = gl.createProgram();
  shaders.forEach(shader => gl.attachShader(program, shader)); gl.linkProgram(program);
  if (extension) {
    while (!gl.getProgramParameter(program, extension.COMPLETION_STATUS_KHR)) await delay(20);
  }
  for (const shader of shaders) {
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(shader) || 'Shader compilation failed');
    gl.deleteShader(shader);
  }
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program) || 'Shader linking failed');
  vao = gl.createVertexArray(); uniforms = {};
  for (const name of ['u_resolution','u_time','u_time_delta','u_frame','u_mouse','u_drag','u_scroll']) uniforms[name] = gl.getUniformLocation(program, name);
  gl.disable(gl.BLEND); gl.disable(gl.DEPTH_TEST); gl.disable(gl.CULL_FACE);
  const debug = gl.getExtension('WEBGL_debug_renderer_info');
  postMessage({type:'ready', parallelCompile:!!extension, renderer:debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)});
}
async function render(message) {
  const start = performance.now();
  surface.width = message.width; surface.height = message.height;
  gl.viewport(0,0,message.width,message.height); gl.useProgram(program); gl.bindVertexArray(vao);
  gl.uniform2f(uniforms.u_resolution,message.width,message.height);
  gl.uniform1f(uniforms.u_time,message.time); gl.uniform1f(uniforms.u_time_delta,message.delta);
  gl.uniform1i(uniforms.u_frame,message.frame); gl.uniform4fv(uniforms.u_mouse,message.mouse);
  gl.uniform2fv(uniforms.u_drag,message.drag); gl.uniform1f(uniforms.u_scroll,message.scroll);
  // Scissors retain full-frame coordinates and equations, while bounding each submission.
  gl.enable(gl.SCISSOR_TEST);
  for (let y=0;y<message.height;y+=32) for (let x=0;x<message.width;x+=32) {
    gl.scissor(x,y,Math.min(32,message.width-x),Math.min(32,message.height-y));
    gl.drawArrays(gl.TRIANGLES,0,3); await waitForGPU();
  }
  gl.disable(gl.SCISSOR_TEST);
  const error = gl.getError(); if (error !== gl.NO_ERROR) throw Error(`WebGL error ${error}`);
  const bitmap = surface.transferToImageBitmap();
  postMessage({type:'frame',bitmap,time:message.time,width:message.width,height:message.height,elapsed:performance.now()-start},[bitmap]);
}
onmessage = event => {
  if (event.data.type === 'probe') {
    try { probe(); } catch(error) { postMessage({type:'error',message:String(error.message || error)}); }
    return;
  }
  const action = event.data.type === 'init' ? initialize : render;
  action(event.data).catch(error => postMessage({type:'error',message:String(error.message || error)}));
};
