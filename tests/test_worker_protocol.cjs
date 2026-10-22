// Protocol tests use a mock GL implementation; they do not certify GPU execution.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../viewer/worker.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function harness({parallel = true, invalidFragment = false} = {}) {
  const messages = [], timers = [];
  let completed = false, statusQueries = 0, draws = 0, clock = 0;
  const gl = {
    VERTEX_SHADER:1, FRAGMENT_SHADER:2, COMPILE_STATUS:3, LINK_STATUS:4,
    RENDERER:5, VERSION:6,
    getExtension: name => name === 'KHR_parallel_shader_compile' && parallel ? {COMPLETION_STATUS_KHR:7} : null,
    getParameter: name => name === 5 ? 'Mock GL; not a GPU result' : 'Mock version',
    createShader: type => ({type}), shaderSource(){}, compileShader(){},
    createProgram: () => ({}), attachShader(){}, linkProgram(){},
    getProgramParameter: (_, name) => name === 7 ? completed : true,
    getShaderParameter: shader => {statusQueries++; return !(invalidFragment && shader.type === 2);},
    getShaderInfoLog: () => 'deliberate mock compile error', deleteShader(){},
    createVertexArray: () => ({}), getUniformLocation: () => ({}), disable(){},
    drawArrays(){draws++;},
  };
  const context = vm.createContext({
    performance:{now:() => ++clock},
    postMessage: message => messages.push(message),
    setTimeout: callback => timers.push(callback),
    OffscreenCanvas:class {getContext(){return gl;} addEventListener(){}},
  });
  vm.runInContext(source, context);
  const send = data => context.onmessage({data});
  return {messages,timers,send,complete:()=>{completed=true;},
          statusQueries:()=>statusQueries, draws:()=>draws};
}

(async () => {
  const pending = harness();
  pending.send({type:'probe'});
  pending.send({type:'init',vertex:'mock',fragment:'mock'});
  await tick();
  assert.equal(pending.messages.at(-1).stage, 'parallel-completion-wait');
  assert.equal(pending.statusQueries(), 0, 'do not query synchronous status before completion');
  assert.equal(pending.messages.some(message => message.type === 'ready'), false);
  assert.equal(pending.draws(), 0);
  pending.complete();
  pending.timers.shift()();
  await tick();
  const stages = pending.messages.filter(message => message.type === 'progress').map(message => message.stage);
  assert.deepEqual(stages, ['vertex-compile-call','vertex-compile-returned',
    'fragment-compile-call','fragment-compile-returned','link-call','link-returned',
    'parallel-completion-wait','status-queries']);
  assert.equal(pending.messages.at(-1).type, 'ready');
  assert.ok(pending.messages.at(-1).compileElapsedMs > 0);
  assert.equal(pending.draws(), 0, 'compilation protocol never implies a rendered frame');

  const failed = harness({parallel:false,invalidFragment:true});
  failed.send({type:'probe'});
  failed.send({type:'init',vertex:'mock',fragment:'mock'});
  await tick();
  assert.equal(failed.messages.at(-1).type, 'error');
  assert.equal(failed.messages.at(-1).message, 'deliberate mock compile error');
  assert.equal(failed.messages.some(message => message.type === 'ready'), false);
  assert.ok(failed.messages.some(message => message.stage === 'no-parallel-extension'));
  assert.equal(failed.draws(), 0);
  console.log('PASS: pending compilation, completion ordering, error propagation; mock GL only');
})().catch(error => {console.error(error);process.exitCode=1;});
