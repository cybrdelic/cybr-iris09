(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {width:160,height:90,time:0,drag:[0,0],scroll:0,samples:2};
  let revision=0, busy=false, timer=null, activated=false, currentURL=null, pointer=null;
  const clamp=(n,lo,hi)=>Math.min(hi,Math.max(lo,n));
  const snapshot=()=>({...state,drag:[...state.drag],requestId:revision});
  function status(message){$('status').textContent=message;}
  function failure(message){$('error').textContent=message;$('error').hidden=false;}
  function changed(){
    revision++;activated=true;$('timeValue').textContent=state.time.toFixed(2)+' s';$('zoomValue').textContent=state.scroll.toFixed(2);
    clearTimeout(timer);timer=setTimeout(render,200);
    if(busy)status('Rendering a previous request; your latest controls will render next. The displayed image keeps its completed label.');
  }
  function pngURL(base64){
    const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));
    return URL.createObjectURL(new Blob([bytes],{type:'image/png'}));
  }
  async function render(){
    if(busy||!activated)return;
    const requested=snapshot();busy=true;$('render').disabled=true;$('error').hidden=true;
    status(`Rendering native ${requested.width} x ${requested.height}, AA${requested.samples}, time ${requested.time.toFixed(2)} s...`);
    let succeeded=false;const controller=new AbortController();
    const requestDeadline=setTimeout(()=>controller.abort(),125000);
    try{
      const response=await fetch('/api/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(requested),signal:controller.signal});
      const result=await response.json();
      if(!response.ok)throw Error(result.error||'Native preview request failed.');
      if(result.requestId!==requested.requestId)throw Error('Native response did not match its request.');
      if(requested.requestId!==revision)return;
      const url=pngURL(result.png), image=new Image();
      try{
        image.src=url;await image.decode();
        if(requested.requestId!==revision){URL.revokeObjectURL(url);return;}
        if(image.naturalWidth!==requested.width||image.naturalHeight!==requested.height)throw Error('Native image size differs from the request.');
        $('frame').src=url;$('frame').hidden=false;$('placeholder').hidden=true;
        if(currentURL)URL.revokeObjectURL(currentURL);currentURL=url;
        $('completed').textContent=`Completed native OpenGL frame: time ${requested.time.toFixed(2)} s; ${requested.width} x ${requested.height}; AA${requested.samples}; drag ${requested.drag.map(n=>n.toFixed(2)).join(', ')}; zoom ${requested.scroll.toFixed(2)}. Render ${Math.round(result.elapsedMs)} ms.`;
        status('Native frame ready. Drag, zoom or change time to request another.');succeeded=true;
      }catch(error){URL.revokeObjectURL(url);throw error;}
    }catch(error){if(requested.requestId===revision){failure(error.message);status('Native preview failed. The previous completed frame, if any, is retained.');}}
    finally{
      clearTimeout(requestDeadline);busy=false;$('render').disabled=false;
      // One request at a time. A superseded frame cannot overwrite newer controls.
      if(requested.requestId!==revision){clearTimeout(timer);timer=setTimeout(render,0);}
      else if(!succeeded)$('render').textContent='Retry native preview';
      else $('render').textContent='Render preview';
    }
  }
  $('render').addEventListener('click',()=>{activated=true;clearTimeout(timer);render();});
  $('time').addEventListener('input',()=>{state.time=Number($('time').value);changed();});
  $('zoom').addEventListener('input',()=>{state.scroll=Number($('zoom').value);changed();});
  $('samples').addEventListener('change',()=>{state.samples=Number($('samples').value);changed();});
  $('size').addEventListener('change',()=>{
    const [width,height]=$('size').value.split('x').map(Number);
    state.drag=[clamp(state.drag[0]*width/state.width,-8192,8192),clamp(state.drag[1]*height/state.height,-8192,8192)];
    state.width=width;state.height=height;changed();
  });
  $('reset').addEventListener('click',()=>{state.time=0;state.drag=[0,0];state.scroll=0;$('time').value='0';$('zoom').value='0';changed();});
  const stage=$('stage');
  stage.addEventListener('pointerdown',event=>{
    if(event.button!==0)return;pointer={id:event.pointerId,x:event.clientX,y:event.clientY};stage.setPointerCapture(event.pointerId);stage.focus();
  });
  stage.addEventListener('pointermove',event=>{
    if(!pointer||pointer.id!==event.pointerId)return;
    const box=stage.getBoundingClientRect();
    state.drag[0]=clamp(state.drag[0]+(event.clientX-pointer.x)*state.width/box.width,-8192,8192);
    state.drag[1]=clamp(state.drag[1]-(event.clientY-pointer.y)*state.height/box.height,-8192,8192);
    pointer.x=event.clientX;pointer.y=event.clientY;changed();
  });
  const release=event=>{if(pointer?.id===event.pointerId){if(stage.hasPointerCapture(event.pointerId))stage.releasePointerCapture(event.pointerId);pointer=null;}};
  stage.addEventListener('pointerup',release);stage.addEventListener('pointercancel',release);
  stage.addEventListener('wheel',event=>{
    event.preventDefault();const units=event.deltaMode===1?16:event.deltaMode===2?stage.clientHeight:1;
    state.scroll=clamp(state.scroll+event.deltaY*units*.001,-2,2);$('zoom').value=String(state.scroll);changed();
  },{passive:false});
  stage.addEventListener('keydown',event=>{
    const move={ArrowLeft:[-8,0],ArrowRight:[8,0],ArrowUp:[0,8],ArrowDown:[0,-8]}[event.key];
    if(!move)return;event.preventDefault();state.drag=state.drag.map((n,i)=>clamp(n+move[i],-8192,8192));changed();
  });
  window.addEventListener('pagehide',()=>{clearTimeout(timer);if(currentURL)URL.revokeObjectURL(currentURL);});
})();
