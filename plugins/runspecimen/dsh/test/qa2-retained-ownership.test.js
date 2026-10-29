import {test} from 'node:test';
import assert from 'node:assert/strict';
import {runCli} from '../lib/cli.js';
import {captureProcess} from '../lib/process.js';

test('QA2 retained ownership: helper loss never authorizes parent destructive group signals',async()=>{
  const realKill=process.kill;let child;const destructive=[];
  process.kill=(pid,sig)=>{
    if(child && pid===-child.pid){if(sig!==0)destructive.push(sig);return true;}
    return realKill(pid,sig);
  };
  try{
    await assert.rejects(captureProcess({command:process.execPath,argv:['-e','process.exit(0)'],cwd:process.cwd(),timeoutMs:1000,graceMs:20,onData(){},onSpawn(c){child=c;realKill(c.pid,'SIGKILL');}}),e=>e.cleanupConfirmed===false);
    assert.deepEqual(destructive,[]);
  }finally{process.kill=realKill;}
});

test('QA2 retained ownership: real leftover child is gone before returning CLI completion',async()=>{
  const r=await runCli({command:process.execPath,argv:['-e',`
const {spawn}=require('node:child_process');
const child=spawn(process.execPath,['-e',"process.on('SIGTERM',()=>{});setInterval(()=>{},1000)"],{stdio:'ignore'});
console.log(child.pid);child.unref();
`],cwd:process.cwd(),timeoutMs:3000,graceMs:20,maxOutputBytes:1024});
  const pid=Number(r.text.split('\n')[0]);assert.ok(pid>0);
  assert.throws(()=>process.kill(pid,0),{code:'ESRCH'});
  assert.equal(r.cliExitCode,0);assert.equal(r.cliOutcomeObserved,true);
});
