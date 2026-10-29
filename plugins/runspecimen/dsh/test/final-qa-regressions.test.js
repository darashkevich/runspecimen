import {test} from 'node:test';
import assert from 'node:assert/strict';
const source = process.env.DSH_QA_SOURCE_URL ?? new URL('../',import.meta.url).href;
const {runCli} = await import(new URL('lib/cli.js',source));
const {DashboardManager} = await import(new URL('lib/dashboard.js',source));
const options = {command:process.execPath,cwd:process.cwd(),timeoutMs:200,graceMs:50,maxOutputBytes:256};

test('budget expiry is distinct from caller cancellation',async()=>{
  const result = await runCli({...options,argv:['-e','setInterval(()=>{},1000)']});
  assert.equal(result.exitCode,-1);
  assert.equal(result.cancelled,false);
  assert.equal(result.timedOut,true);
  assert.equal(result.cleanupFailed,false);
});

test('persistent EPERM inspection produces bounded structured cleanup failure',async()=>{
  const realKill = process.kill;
  process.kill = (pid,signal)=>{
    if(pid<0 && signal===0){const e=new Error('fixture inspection denied');e.code='EPERM';throw e;}
    return realKill(pid,signal);
  };
  try {
    const result = await runCli({...options,argv:['-e','setInterval(()=>{},1000)']});
    assert.equal(result.exitCode,-1);
    assert.equal(result.cleanupFailed,true);
    assert.equal(result.cancelled,false);
    assert.match(result.termination,/cleanup could not be confirmed/);
  } finally {process.kill=realKill;}
});

test('dashboard reports and enforces its configured maximum lifetime',async()=>{
  const manager = new DashboardManager();
  try {
    const started=await manager.start({...options,timeoutMs:400,argv:['-e',"console.log('http://127.0.0.1:12345/');setInterval(()=>{},1000)"]});
    assert.equal(started.running,true);
    const entry=manager.entries.get(started.pid);
    assert.ok(entry);
    const result=await entry.done;
    assert.equal(started.lifetimeMs,400);
    assert.equal(result.cleaned,true);
    assert.equal(manager.entries.has(started.pid),false);
    assert.throws(()=>process.kill(started.pid,0),{code:'ESRCH'});
  } finally {await manager.dispose();}
});

test('normal parent exit with surviving descendant returns typed cleanup result',async()=>{
  const descendant = "process.on('SIGTERM',()=>{});process.send('ready');setInterval(()=>{},1000)";
  const parent = `const {spawn}=require('node:child_process');const child=spawn(process.execPath,['-e',${JSON.stringify(descendant)}],{stdio:['ignore','ignore','ignore','ipc']});child.once('message',()=>{child.disconnect();child.unref();});`;
  const result=await runCli({...options,timeoutMs:3000,argv:['-e',parent]});
  assert.equal(result.exitCode,-1);
  assert.equal(result.terminationKind,'cleanup');
  assert.equal(result.cleanupFailed,false);
  assert.equal(result.cancelled,false);
  assert.match(result.termination,/leaving child processes/);
});
