import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ChildProcess} from 'node:child_process';
import {once} from 'node:events';
import {mkdtempSync,writeFileSync,readFileSync,watch,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const source=process.env.DSH_QA_SOURCE_URL ?? new URL('../',import.meta.url).href;
const {apply}=await import(new URL('lib/index.js',source));

function ready(directory) {
  return new Promise((resolve,reject)=>{
    const watcher=watch(directory,check);
    const timer=setTimeout(()=>{watcher.close();reject(Error('private fixture readiness deadline'));},10000);
    function check(){try{if(readFileSync(join(directory,'ready'),'utf8')){clearTimeout(timer);watcher.close();resolve();}}catch{}}
    check();
  });
}

for(const mode of ['timeout','cancel'])test(`ordinary registered status retains ${mode} when cleanup delivery fails`,async()=>{
  const directory=mkdtempSync(join(tmpdir(),'dsh-ordinary-cause-'));
  const fixture=join(directory,'hanging-cli.mjs');
  writeFileSync(fixture,`#!${process.execPath}\nimport {writeFileSync} from 'node:fs';\nwriteFileSync(${JSON.stringify(join(directory,'ready'))},String(process.pid));\nsetInterval(()=>{},1000);\n`,{mode:0o700});
  const original=ChildProcess.prototype.emit,children=[];
  let destructiveSignals=0;const realKill=process.kill;
  ChildProcess.prototype.emit=function(event,...args){
    if(event==='spawn' && this.send){
      children.push(this);const send=this.send;
      this.send=function(message,...rest){
        if(message?.type==='cleanup'){
          queueMicrotask(()=>rest.at(-1)(Object.assign(Error('modeled cleanup delivery denied'),{code:'EPERM'})));
          return false;
        }
        return send.call(this,message,...rest);
      };
    }
    return original.call(this,event,...args);
  };
  process.kill=(pid,signal)=>{if(pid<0 && signal!==0){destructiveSignals++;throw Error('parent destructive group signal forbidden');}return realKill(pid,signal);};
  const all=[],disposers=[];const controller=new AbortController();
  try {
    apply({tools:{register:t=>all.push(t)},systemPrompt:{section(){},getSectionOrder(){return 1;}},effect:f=>disposers.push(f())},
      {command:fixture,timeoutMs:mode==='timeout'?3000:10000,graceMs:20});
    const pending=all.find(t=>t.name==='runspecimen_status').execute({workspace:directory,campaign_id:"fixture-campaign",run_id:"fixture-run"},{signal:controller.signal});
    await ready(directory);
    if(mode==='cancel')controller.abort();
    const result=await pending;
    assert.equal(result.ok,false);assert.equal(result.exitCode,-1);assert.equal(result.cleanupFailed,true);
    assert.equal(result.timedOut,mode==='timeout');assert.equal(result.cancelled,mode==='cancel');
    assert.equal(result.terminationKind,'cleanup');
    assert.equal(result.triggerKind,mode==='timeout'?'timeout':'cancelled');
    assert.match(result.output,mode==='timeout'?/exceeded its 3000ms budget/:/cancelled by the caller/);
    assert.match(result.output,/cleanup request failed.*modeled cleanup delivery denied/);
    assert.equal(destructiveSignals,0);
  } finally {
    ChildProcess.prototype.emit=original;process.kill=realKill;
    for(const child of children){
      const exited=child.exitCode!==null || child.signalCode!==null ? Promise.resolve() : once(child,'exit');
      if(child.connected)child.disconnect();
      await exited;
    }
    for(const dispose of disposers)await dispose();
    rmSync(directory,{recursive:true,force:true});
  }
});
