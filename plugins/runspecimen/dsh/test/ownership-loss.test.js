import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {captureProcess} from '../lib/process.js';

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

test('leader loss after TERM forbids escalation and preserves cleanup failure', async()=>{
  const original=process.kill;
  let child;
  const signals=[];
  process.kill=(pid,signal)=>{
    if(child && pid===-child.pid){
      if(signal===0)return true;
      signals.push(signal);
      if(signal==='SIGTERM')original(child.pid,'SIGKILL');
      return true;
    }
    return original(pid,signal);
  };
  try {
    await assert.rejects(captureProcess({command:process.execPath,argv:['-e','process.exit(0)'],cwd:process.cwd(),timeoutMs:1000,graceMs:100,onData(){},onSpawn(c){child=c;}}), e=>e.kind==='cleanup' && e.cleanupConfirmed===false);
    assert.deepEqual(signals,['SIGTERM'], 'No grace/deadline KILL after the pinned leader dies');
  } finally {process.kill=original;}
});

test('supervisor exit zero without command acknowledgement cannot claim success', async()=>{
  const previous=process.env.NODE_OPTIONS;
  process.env.NODE_OPTIONS='--import=data:text/javascript,'+encodeURIComponent("if(process.argv[1]?.endsWith('/group-supervisor.js'))process.exit(0)");
  try {
    await assert.rejects(captureProcess({command:process.execPath,argv:['-e','console.log("CLI_ACTUALLY_EXECUTED")'],cwd:process.cwd(),timeoutMs:1000,graceMs:10,onData(){}}), /without.*command.*outcome/);
  } finally {if(previous===undefined)delete process.env.NODE_OPTIONS;else process.env.NODE_OPTIONS=previous;}
});


test('package includes the mandatory group supervisor',()=>{
  const manifest=JSON.parse(readFileSync(new URL('../package.json',import.meta.url),'utf8'));
  assert.ok(manifest.files.includes('lib/group-supervisor.js'));
});
