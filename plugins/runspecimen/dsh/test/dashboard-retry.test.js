import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {apply} from '../lib/index.js';
import {retryOwnedGroup} from '../lib/process.js';
import {spawn,ChildProcess} from 'node:child_process';
import {once} from 'node:events';
import {mkdtempSync,readFileSync,rmSync,watch} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

function ready(directory) {
  const file=join(directory,'ready');
  const read=()=>{try{return Number(readFileSync(file,'utf8'));}catch{return null;}};
  return new Promise((resolve,reject)=>{
    const w=watch(directory,()=>check());
    const timer=setTimeout(()=>{w.close();reject(Error('fixture readiness deadline'));},10000);
    const check=()=>{const pid=read();if(pid){clearTimeout(timer);w.close();resolve(pid);}};
    check();
  });
}

function tools(config={}) {
  const all=[],disposers=[];
  apply({tools:{register:t=>all.push(t)},systemPrompt:{section(){},getSectionOrder(){return 1;}},
    effect:f=>disposers.push(f())},{command:fileURLToPath(new URL('./fixtures/dashboard-cli.mjs',import.meta.url)),
    timeoutMs:10000,graceMs:20,...config});
  return {get:name=>all.find(t=>t.name===`runspecimen_${name}`),dispose:async()=>{for(const f of disposers)await f();}};
}

function ipcFault() {
  const original=ChildProcess.prototype.emit,children=[];
  let denied=false;
  ChildProcess.prototype.emit=function(event,...args){
    if(event==='spawn' && this.send){
      const child=this,send=child.send;
      children.push(()=>{child.send=send;});
      child.send=function(message,...rest){
        if(denied && message?.type==='cleanup'){
          queueMicrotask(()=>rest.at(-1)(Object.assign(new Error('fixture IPC denied'),{code:'EPERM'})));
          return false;
        }
        return send.call(this,message,...rest);
      };
    }
    return original.call(this,event,...args);
  };
  return {deny:value=>{denied=value;},restore(){denied=false;ChildProcess.prototype.emit=original;for(const restore of children)restore();}};
}

test('IPC delivery failure retains ownership and registered Stop really retries after restore',async()=>{
  const owner=tools();const realKill=process.kill,fault=ipcFault();let pid;
  try {
    const started=await owner.get('dashboard').execute({workspace:'/tmp',contract:'fixture.json'},{});
    pid=Number(started.output.match(/pid (\d+)/)[1]);
    fault.deny(true);
    const failed=await owner.get('dashboard_stop').execute({pid},{});
    assert.equal(failed.cleanupFailed,true);
    realKill(pid,0);
    fault.restore();
    const retried=await owner.get('dashboard_stop').execute({pid},{});
    assert.equal(retried.ok,true,'owned live dashboard must remain retryable');
    assert.throws(()=>realKill(pid,0),{code:'ESRCH'});
    const again=await owner.get('dashboard_stop').execute({pid},{});
    assert.equal(again.ok,false,'confirmed-dead entry must be removed');
  } finally {fault.restore();process.kill=realKill;if(pid){try{realKill(-pid,'SIGKILL');}catch{}}await owner.dispose();}
});

for(const mode of ['timeout','cancel']) {
  test(`registered dashboard preserves ${mode} and waits for cleanup`,async()=>{
    const directory=mkdtempSync(join(tmpdir(),'dsh-start-outcome-'));
    const owner=tools({command:fileURLToPath(new URL('./fixtures/silent-dashboard.mjs',import.meta.url)),timeoutMs:mode==='cancel'?10000:1500});
    const controller=new AbortController();
    try {
      const pending=owner.get('dashboard').execute({workspace:directory,contract:'fixture.json'},{signal:controller.signal});
      const pid=await ready(directory);
      if(mode==='cancel')controller.abort();
      const result=await pending;
      assert.equal(result.ok,false);
      assert.equal(result.timedOut,mode==='timeout');
      assert.equal(result.cancelled,mode==='cancel');
      assert.equal(result.cleanupFailed,false);
      assert.throws(()=>process.kill(pid,0),{code:'ESRCH'});
      if(mode==='timeout')assert.doesNotMatch(result.output,/cancelled by the caller/);
    } finally {await owner.dispose();rmSync(directory,{recursive:true,force:true});}
  });
}

test('cleanup retry never signals a group once its original leader was reaped',async()=>{
  const child=spawn(process.execPath,['-e',"process.send('ready');setInterval(()=>{},1000)"],{detached:true,stdio:['ignore','ignore','ignore','ipc']});
  const realKill=process.kill;let signals=0;
  await once(child,'message');
  try {
    process.kill=(pid,signal)=>{if(pid===-child.pid && signal!==0)signals++;return realKill(pid,signal);};
    // A stale/reused numeric PID must not become authority over this live group.
    await assert.rejects(retryOwnedGroup({pid:child.pid,exitCode:0,signalCode:null},20),/possibly reused/);
    assert.equal(signals,0);
    realKill(child.pid,0);
  } finally {process.kill=realKill;realKill(-child.pid,'SIGKILL');await once(child,'close');}
});

test('startup cleanup failure preserves the originating timeout flag',async()=>{
  const directory=mkdtempSync(join(tmpdir(),'dsh-start-cleanup-'));
  const owner=tools({command:fileURLToPath(new URL('./fixtures/silent-dashboard.mjs',import.meta.url)),timeoutMs:1500});
  const realKill=process.kill,fault=ipcFault();let pid;
  try {
    const pending=owner.get('dashboard').execute({workspace:directory,contract:'fixture.json'},{});
    pid=await ready(directory);
    fault.deny(true);
    const result=await pending;
    assert.equal(result.cleanupFailed,true);
    assert.equal(result.timedOut,true);
    assert.equal(result.cancelled,false);
  } finally {fault.restore();process.kill=realKill;await owner.dispose();if(pid){try{realKill(-pid,'SIGKILL');}catch{}}rmSync(directory,{recursive:true,force:true});}
});
