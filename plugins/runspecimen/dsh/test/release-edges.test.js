import {test,after} from 'node:test';
// Keep the harness alive for implementations that unref their own deadline.
const harnessGuard=setTimeout(()=>{},20000);after(()=>clearTimeout(harnessGuard));
import assert from 'node:assert/strict';
import {spawn,execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {once} from 'node:events';
import {mkdtempSync,watch,readFileSync,rmSync,realpathSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
const source=process.env.DSH_QA_SOURCE_URL ?? new URL('../',import.meta.url).href;
const {runCli,startDashboard,stopDashboard,boundOutput}=await import(new URL('lib/cli.js',source));
const {apply,Config}=await import(new URL('lib/index.js',source));
const fixture=fileURLToPath(new URL('./fixtures/release-edge.mjs',import.meta.url));
const dashboardFixture=fileURLToPath(new URL('./fixtures/fake-runspecimen.mjs',import.meta.url));
const base={command:process.execPath,timeoutMs:1500,maxOutputBytes:256,graceMs:100};
function alive(pid){try{process.kill(pid,0);return true;}catch{return false;}}
function kill(pid){try{process.kill(pid,'SIGKILL');}catch{}}
function tools(config={}){const all=[],dispose=[];apply({tools:{register:t=>all.push(t)},systemPrompt:{section(){},getSectionOrder(){return 1;}},effect:f=>dispose.push(f())},{command:process.execPath,...config});return {all,dispose:async()=>{for(const fn of dispose)await fn();}};}
async function ready(dir,file){const read=()=>{try{return JSON.parse(readFileSync(file));}catch{return null;}};let v=read();if(v)return v;return new Promise((resolve,reject)=>{const w=watch(dir,()=>{const v=read();if(v){w.close();clearTimeout(t);resolve(v);}});const t=setTimeout(()=>{w.close();reject(Error('fixture readiness timeout'));},10000);v=read();if(v){w.close();clearTimeout(t);resolve(v);}});}
test('parent exit does not cancel escalation for surviving descendants',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'dsh-edge-')),file=join(dir,'ready');const controller=new AbortController();let ids;
 try {const pending=runCli({...base,argv:[fixture,'cooperative-tree',file],signal:controller.signal});ids=await ready(dir,file);controller.abort();const r=await pending;assert.equal(r.cancelled,true);assert.equal(alive(ids.pid),false);assert.equal(alive(ids.descendant),false,'descendant must be gone at completion');}
 finally{if(ids){kill(ids.pid);kill(ids.descendant);}rmSync(dir,{recursive:true,force:true});}
});
test('dashboard stop cannot signal an unrelated live PID',async()=>{
 const child=spawn(process.execPath,['-e',"process.send('ready');setInterval(()=>{},10000)"],{detached:true,stdio:['ignore','ignore','ignore','ipc']});await once(child,'message');
 try {const t=tools().all.find(t=>t.name==='runspecimen_dashboard_stop');const r=await t.execute({pid:child.pid},{});assert.equal(r.ok,false);assert.equal(alive(child.pid),true);}
 finally{kill(child.pid);if(child.exitCode===null && child.signalCode===null)await once(child,'close');}
});
test('stderr retains the late error after its early output overflows',async()=>{const r=await runCli({...base,argv:[fixture,'stderr-tail']});assert.equal(r.truncated,true);assert.match(r.text,/IMPORTANT_LATE_ERROR/);});
test('small capture budget bounds retained bytes including stderr',async()=>{const r=await runCli({...base,argv:[fixture,'stderr-size']});const prefix=r.text.split('\n\n[output truncated')[0];assert.ok(Buffer.byteLength(prefix)<=256);});
test('UTF8 helper omits incomplete codepoints',()=>{assert.doesNotMatch(boundOutput('😀😀',3),/�/);});
test('pre-aborted run cannot attempt to execute a missing binary',async()=>{const c=new AbortController();c.abort();const r=await runCli({...base,command:'/missing-dsh-test',argv:[],signal:c.signal});assert.equal(r.cancelled,true);assert.match(r.text,/nothing was started/);});
test('pre-aborted dashboard cannot spawn',async()=>{const c=new AbortController();c.abort();await assert.rejects(startDashboard({...base,command:'/missing-dsh-test',argv:[],signal:c.signal}),/cancelled/);});
test('dashboard without observed URL is stopped, not reported running',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'dsh-start-')),file=join(dir,'ready');let ids;
 try{const pending=startDashboard({...base,timeoutMs:700,argv:[fixture,'no-url',file]});ids=await ready(dir,file);const r=await pending;assert.equal(r.running,false);assert.equal(alive(ids.pid),false);}
 finally{if(ids)kill(ids.pid);rmSync(dir,{recursive:true,force:true});}
});
test('a second plugin instance cannot stop the first instance dashboard',async()=>{
 const exe=fileURLToPath(new URL('./fixtures/dashboard-cli.mjs',import.meta.url));const first=tools({command:exe,timeoutMs:5000}),second=tools();let pid;
 try {const r=await first.all.find(t=>t.name==='runspecimen_dashboard').execute({workspace:tmpdir(),contract:'k.json'},{});assert.equal(r.ok,true);pid=Number(r.output.match(/pid (\d+)/)[1]);const stopped=await second.all.find(t=>t.name==='runspecimen_dashboard_stop').execute({pid},{});assert.equal(stopped.ok,false);assert.equal(alive(pid),true);}
 finally{if(pid)await first.all.find(t=>t.name==='runspecimen_dashboard_stop').execute({pid},{});await first.dispose();await second.dispose();}
});
test('plugin disposal stops the dashboards it owns',async()=>{
 const exe=fileURLToPath(new URL('./fixtures/dashboard-cli.mjs',import.meta.url));const owner=tools({command:exe,timeoutMs:5000});let pid;
 try{const r=await owner.all.find(t=>t.name==='runspecimen_dashboard').execute({workspace:tmpdir(),contract:'k.json'},{});assert.equal(r.ok,true);pid=Number(r.output.match(/pid (\d+)/)[1]);await owner.dispose();assert.equal(alive(pid),false);}
 finally{if(pid)kill(pid);}
});
test('production paths use session cwd and workspace-relative files',async()=>{
 const exe=fileURLToPath(new URL('./fixtures/argv-cli.mjs',import.meta.url));const t=tools({command:exe}).all.find(t=>t.name==='runspecimen_validate');const r=await t.execute({workspace:'ws',contract:'k.json'},{agent:{session:{header:{cwd:tmpdir()}}}});const data=JSON.parse(r.output);assert.equal(data.cwd,realpathSync(tmpdir()));assert.deepEqual(data.argv,['validate','--workspace',resolve(tmpdir(),'ws'),'--contract',resolve(tmpdir(),'ws/k.json')]);
});

test('schema and apply reject fractional and excessive resource limits',()=>{
 for(const config of [{timeoutMs:1.5},{timeoutMs:3600001},{maxOutputBytes:1.5},{maxOutputBytes:4194305},{graceMs:1.5},{graceMs:10001}]){assert.throws(()=>Config(config));assert.throws(()=>apply({tools:{register(){}},systemPrompt:{section(){},getSectionOrder(){return 1;}}},config));}
});
test('64 MiB producer fits a 48 MiB parent heap with bounded capture',async()=>{
 const probe=fileURLToPath(new URL('./fixtures/bounded-capture-probe.mjs',import.meta.url));const {stdout}=await promisify(execFile)(process.execPath,['--max-old-space-size=48',probe,new URL('lib/cli.js',source).href],{timeout:20000,maxBuffer:16000});const result=JSON.parse(stdout);assert.equal(result.exitCode,0);assert.equal(result.truncated,true);assert.ok(result.bytes<1024);
});

test('package and lockfile agree on Apache-2.0 licensing',()=>{
 const manifest=JSON.parse(readFileSync(new URL('package.json',source),'utf8'));
 const lock=JSON.parse(readFileSync(new URL('package-lock.json',source),'utf8'));
 assert.equal(manifest.license,'Apache-2.0');
 assert.equal(lock.packages[''].license,manifest.license);
});

test('dashboard tool reports the enforced configured lifetime',async()=>{
 const exe=fileURLToPath(new URL('./fixtures/dashboard-cli.mjs',import.meta.url));
 const owner=tools({command:exe,timeoutMs:1200});
 try {
  const result=await owner.all.find(t=>t.name==='runspecimen_dashboard').execute({workspace:tmpdir(),contract:'k.json'},{});
  assert.equal(result.ok,true);
  assert.match(result.output,/Maximum lifetime: 1200 ms from launch/);
 } finally {await owner.dispose();}
});
