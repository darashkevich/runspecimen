import {captureProcess,validateLimits,ProcessCaptureError,retryOwnedGroup} from './process.js';
import {StringDecoder} from 'node:string_decoder';

/** Dashboards belong to a plugin instance, never to arbitrary caller PIDs. */
export class DashboardManager {
  entries=new Map();
  async start({command,argv,cwd,signal,timeoutMs=15000,graceMs=250}) {
    validateLimits(timeoutMs,8192);
    if(process.platform==='win32')throw new Error('Windows dashboard cleanup is not supported');
    if(signal?.aborted) throw new ProcessCaptureError('Dashboard start cancelled; nothing was started','cancelled');
    const controller=new AbortController();let entry;let readyResolve;let decided=false;let observed='';let size=0;
    const ready=new Promise(resolve=>{readyResolve=resolve;});
    const decide=value=>{if(decided)return;decided=true;readyResolve(value);};
    const decoder=new StringDecoder('utf8');
    const onAbort=()=>controller.abort();signal?.addEventListener('abort',onAbort,{once:true});
    const startup=setTimeout(()=>{controller.abort(new ProcessCaptureError(`Dashboard startup exceeded its ${Math.min(timeoutMs,15000)}ms budget`,'timeout'));decide(null);},Math.min(timeoutMs,15000));
    const done=captureProcess({command,argv,cwd,signal:controller.signal,timeoutMs,graceMs,
      onSpawn:child=>{if(child.pid){entry={pid:child.pid,child,controller,graceMs,done:null,state:'running',retry:null};this.entries.set(child.pid,entry);}},
      onData:chunk=>{
        const count=Math.min(chunk.length,8192-size);if(count<=0)return;
        size+=count;observed+=decoder.write(chunk.subarray(0,count));
        const match=observed.match(/http:\/\/(?:127\.0\.0\.1|localhost|\[::1\]):\d+\/?(?=[\s"'<>])/);
        if(match && !controller.signal.aborted)decide(match[0]);
      }
    }).then(()=>{decide(null);return {cleaned:true};},error=>{decide(null);return {error,cleaned:error.cleanupConfirmed !== false};}).then(result=>{
      if(entry && this.entries.get(entry.pid)===entry){
        if(result.cleaned)this.entries.delete(entry.pid);
        else {entry.state='unresolved';entry.cleanupError=result.error;}
      }
      return result;
    });
    if(entry)entry.done=done;
    try {
      const url=await ready;
      if(!url || signal?.aborted || !entry || !this.entries.has(entry.pid)) {
        controller.abort();const result=await done;
        if(!result.cleaned)throw result.error;
        return {url:null,pid:null,text:[observed,result.error?.message].filter(Boolean).join('\n') || "Dashboard exited before serving",running:false,
          timedOut:result.error?.kind==='timeout',cancelled:result.error?.kind==='cancelled',cleanupFailed:false};
      }
      return {url,pid:entry.pid,text:observed,running:true,lifetimeMs:timeoutMs,timedOut:false,cancelled:false,cleanupFailed:false};
    } finally {clearTimeout(startup);signal?.removeEventListener('abort',onAbort);}
  }
  async stop(pid) {
    const entry=this.entries.get(pid);
    if(!entry)return false;
    if(entry.state==='unresolved'){
      entry.retry ??= retryOwnedGroup(entry.child,entry.graceMs).then(()=>{
        if(this.entries.get(pid)===entry)this.entries.delete(pid);
      }).catch(error=>{entry.cleanupError=error;throw error;}).finally(()=>{entry.retry=null;});
      await entry.retry;
      return true;
    }
    entry.controller.abort();const result=await entry.done;
    if(!result.cleaned)throw result.error;
    return true;
  }
  async dispose() {await Promise.all([...this.entries.keys()].map(pid=>this.stop(pid)));}
}
const standalone=new DashboardManager();
export const startDashboard=options=>standalone.start(options);
export const stopDashboard=pid=>standalone.stop(pid);
