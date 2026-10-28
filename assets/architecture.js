'use strict';
// This is a user-controlled explanatory replay of recorded stages, not a live trace.
document.querySelectorAll('.research-network').forEach(root=>{
 const topology=root.querySelector('[data-net-topology]');
 const controls=root.querySelector('.net-controls');
 const button=root.querySelector('[data-net-play]');
 const stages=[...root.querySelectorAll('[data-net-stage]')];
 const selectors=[...root.querySelectorAll('[data-net-select]')];
 let selected=0,timer=null;
 function stop(){if(timer!==null)clearInterval(timer);timer=null;button.textContent=button.dataset.playLabel;topology.removeAttribute('data-animate');}
 function show(index,animated){selected=index;topology.dataset.phase=String(index);topology.removeAttribute('data-animate');
   stages.forEach((stage,i)=>{stage.hidden=i!==index});
   selectors.forEach((item,i)=>item.setAttribute('aria-pressed',String(i===index)));
   if(animated&&!matchMedia('(prefers-reduced-motion: reduce)').matches){void topology.offsetWidth;topology.dataset.animate='yes';}
 }
 selectors.forEach((item,i)=>item.addEventListener('click',()=>{stop();show(i,true)}));
 button.addEventListener('click',()=>{if(timer!==null){stop();return}show(0,false);button.textContent=button.dataset.stopLabel;timer=setInterval(()=>{if(selected>=stages.length-1){stop();return}show(selected+1,true)},1800)});
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stop()});
 controls.hidden=false;show(0,false);
});
