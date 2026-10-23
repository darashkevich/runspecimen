import {spawn} from 'node:child_process';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=process.env.DSH_QA_SOURCE_URL ?? new URL('../',import.meta.url).href;
const {captureProcess}=await import(new URL('lib/process.js',source));

test('reaped leader never authorizes signals to a modeled reused group', async()=>{
  const original=process.kill;
  let child;
  const unsafe=[];
  process.kill=(pid,signal)=>{
    if(child && pid===-child.pid){
      if(signal!==0 && (child.exitCode!==null || child.signalCode!==null))unsafe.push(signal);
      return true; // model numeric reuse without touching any process
    }
    return original(pid,signal);
  };
  try {
    await assert.rejects(captureProcess({command:process.execPath,argv:['-e','process.exit(0)'],cwd:process.cwd(),timeoutMs:1000,graceMs:10,onData(){},onSpawn(c){child=c;c.once("spawn",()=>original(c.pid,"SIGKILL"));}}), e=>e.cleanupConfirmed===false);
    assert.deepEqual(unsafe,[], 'No TERM/KILL is permitted after ownership is lost');
  } finally {process.kill=original;}
});

test('already reaped supervisor with unpublished exit fields never grants parent signal authority',async()=>{
  const realKill=process.kill;
  const trigger=spawn('/usr/bin/true',[],{stdio:'ignore'});
  const controller=new AbortController();let child,window;
  const destructive=[];
  process.kill=(pid,signal)=>{
    if(child && pid===-child.pid){if(signal!==0)destructive.push(signal);return true;}
    return realKill(pid,signal);
  };
  trigger.on('exit',()=>{
    let probe;try{realKill(child.pid,0);probe='present';}catch(error){probe=error.code;}
    window={probe,exitCode:child.exitCode,signalCode:child.signalCode};
    controller.abort();
  });
  try {
    const pending=captureProcess({command:process.execPath,argv:['-e','process.exit(0)'],cwd:process.cwd(),signal:controller.signal,timeoutMs:2000,graceMs:20,onData(){},onSpawn(c){child=c;realKill(c.pid,'SIGKILL');}});
    // Coalesce both OS exits before libuv dispatches the earlier JS callback.
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,250);
    await assert.rejects(pending,e=>e.cleanupConfirmed===false);
    assert.deepEqual(window,{probe:'ESRCH',exitCode:null,signalCode:null});
    assert.deepEqual(destructive,[],'parent never sends TERM/KILL, even before exit fields publish');
  } finally {process.kill=realKill;}
});

test('supervisor exit zero without command acknowledgement cannot claim success', async()=>{
  const previous=process.env.NODE_OPTIONS;
  process.env.NODE_OPTIONS='--import=data:text/javascript,'+encodeURIComponent("if(process.argv[1]?.endsWith('/group-supervisor.js'))process.exit(0)");
  try {
    await assert.rejects(captureProcess({command:process.execPath,argv:['-e','console.log("CLI_ACTUALLY_EXECUTED")'],cwd:process.cwd(),timeoutMs:1000,graceMs:10,onData(){}}), /without.*command.*outcome/);
  } finally {if(previous===undefined)delete process.env.NODE_OPTIONS;else process.env.NODE_OPTIONS=previous;}
});


test('package includes the mandatory group supervisor',()=>{
  const manifest=JSON.parse(readFileSync(new URL('package.json',source),'utf8'));
  assert.ok(manifest.files.includes('lib/group-supervisor.js'));
});

test('missing cleanup acknowledgement fails closed',async()=>{
  const previous=process.env.NODE_OPTIONS;let child;
  process.env.NODE_OPTIONS='--import=data:text/javascript,'+encodeURIComponent("if(process.argv[1]?.endsWith('/group-supervisor.js')){const send=process.send;process.send=function(message,...args){if(message?.type==='cleanup-ack')return true;return send.call(this,message,...args);};}");
  try {
    await assert.rejects(captureProcess({command:process.execPath,argv:['-e','process.exit(0)'],cwd:process.cwd(),timeoutMs:3000,graceMs:20,onData(){},onSpawn(c){child=c;}}),e=>e.cleanupConfirmed===false && /acknowledgement missing/.test(e.message));
  } finally {if(child?.connected)child.disconnect();if(previous===undefined)delete process.env.NODE_OPTIONS;else process.env.NODE_OPTIONS=previous;}
});

test('parent disconnect during grace kills supervisor and command without parent group signals',async()=>{
  const child=spawn(process.execPath,[new URL('lib/group-supervisor.js',source).pathname,JSON.stringify([process.execPath,'-e',"process.on('SIGTERM',()=>{});console.log(process.pid);setInterval(()=>{},1000)"])],{detached:true,stdio:['ignore','pipe','ignore','ipc']});
  let timer;
  try {
    const pid=await new Promise((resolve,reject)=>{child.stdout.once('data',data=>resolve(Number(String(data).trim())));child.once('error',reject);});
    const closed=new Promise(resolve=>child.once('exit',resolve));
    const acknowledged=new Promise(resolve=>child.on('message',message=>{if(message.type==='cleanup-ack')resolve();}));
    child.send({type:'cleanup',requestId:1,graceMs:10000});
    await acknowledged;
    child.disconnect();
    await Promise.race([closed,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('disconnect cleanup deadline')),3000);})]);
    const {execFileSync}=await import('node:child_process');
    let state;try{state=execFileSync('/bin/ps',['-o','stat=','-p',String(pid)],{encoding:'utf8'}).trim();}catch{state='';}
    assert.ok(!state || state.startsWith('Z'),'command must be dead at supervisor exit');
    child.stdout.destroy();
  } finally {clearTimeout(timer);child.stdout.destroy();if(child.connected)child.disconnect();}
});
