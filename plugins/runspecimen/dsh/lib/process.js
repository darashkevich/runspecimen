import { spawn } from 'node:child_process';
import {fileURLToPath} from 'node:url';

export const MAX_TIMEOUT_MS = 3_600_000;
export const MAX_OUTPUT_BYTES = 4_194_304;
export function validateLimits(timeoutMs, maxOutputBytes) {
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs <= 0 || timeoutMs > MAX_TIMEOUT_MS)
    throw new Error(`timeoutMs must be a positive finite number and integer no greater than ${MAX_TIMEOUT_MS}`);
  if (!Number.isSafeInteger(maxOutputBytes) || maxOutputBytes < 0 || maxOutputBytes > MAX_OUTPUT_BYTES)
    throw new Error(`maxOutputBytes must be an integer between 0 and ${MAX_OUTPUT_BYTES}`);
}

export class ProcessCaptureError extends Error {
  constructor(message, kind, cleanupConfirmed = true, cause) {
    super(message, {cause});
    this.name = 'ProcessCaptureError';
    this.kind = kind;
    this.triggerKind = cause instanceof ProcessCaptureError ? cause.triggerKind : kind;
    this.cleanupConfirmed = cleanupConfirmed;
  }
}

/** Cleanup authority stays inside the supervisor, including retries. */
let cleanupRequestId=0;
function requestCleanup(child, graceMs) {
  return new Promise((resolve,reject)=>{
    if(!child.connected || typeof child.send!=='function') {
      reject(new ProcessCaptureError('Cleanup unresolved: supervisor IPC unavailable; refusing a possibly reused process-group ID','cleanup',false));
      return;
    }
    const requestId=++cleanupRequestId;
    let deadline;
    const finish=error=>{clearTimeout(deadline);child.removeListener('message',ack);error?reject(error):resolve();};
    const ack=message=>{if(message?.type==='cleanup-ack' && message.requestId===requestId)finish();};
    child.on('message',ack);
    deadline=setTimeout(()=>finish(new ProcessCaptureError('Supervisor cleanup acknowledgement missing','cleanup',false)),1000);
    const sent=error=>{if(error)finish(new ProcessCaptureError(`Supervisor cleanup request failed: ${error.message}`,'cleanup',false,error));};
    try {child.send({type:'cleanup',graceMs,requestId},sent);}
    catch(error){sent(error);}
  });
}
export async function retryOwnedGroup(child, graceMs=250) {
  const exists=()=>{
    try {process.kill(-child.pid,0);return true;}
    catch(e){if(e.code==='ESRCH')return false;if(e.code==='EPERM')return true;throw new ProcessCaptureError(`Cleanup retry inspection failed: ${e.message}`,'cleanup',false,e);}
  };
  if(!exists())return;
  await requestCleanup(child,graceMs);
  await new Promise((resolve,reject)=>{
    let poll,deadline;
    const finish=error=>{clearInterval(poll);clearTimeout(deadline);error?reject(error):resolve();};
    const check=()=>{try{if(!exists())finish();}catch(e){finish(e);}};
    poll=setInterval(check,10);
    deadline=setTimeout(()=>finish(new ProcessCaptureError('Cleanup retry could not confirm process-group death','cleanup',false)),graceMs+5000);
    check();
  });
}

/** Own a POSIX process group; do not finish cancellation before cleanup. */
export function captureProcess({command, argv, cwd, signal, timeoutMs, onData, onSpawn, onCommandResult, graceMs=250}) {
  if (process.platform === 'win32') throw new Error('This plugin requires macOS or Linux process-group cleanup; Windows is not supported.');
  if (signal?.aborted) return Promise.reject(new Error('RunSpecimen call cancelled by the caller; nothing was started'));
  return new Promise((resolve, reject) => {
    let settled = false, closed = false, exitCode, stopReason, failure, normalCompletion = false, receivedCommandResult = false;
    let timer, poll, cleanupDeadline, cleanupAcknowledged=false;
    const child = spawn(process.execPath, [fileURLToPath(new URL('./group-supervisor.js',import.meta.url)),JSON.stringify([command,...argv])], {cwd, detached:true, stdio:['ignore','pipe','pipe','ipc'],
      env:{...process.env, NO_COLOR:'1', PYTHONUNBUFFERED:'1'}});
    const groupExists = () => {
      if (!child.pid) return false;
      try { process.kill(-child.pid, 0); return true; }
      catch (e) {
        if (e.code === 'ESRCH') return false;
        if (e.code === 'EPERM') return true; // Exists, but inspection is denied.
        throw new ProcessCaptureError(`Process-group inspection failed: ${e.message}`, 'cleanup', false, e);
      }
    };
    const finish = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer); clearTimeout(cleanupDeadline); clearInterval(poll);
      signal?.removeEventListener('abort', abort);
      if (error) reject(error); else resolve(exitCode ?? -1);
    };
    const check = () => {
      if (!closed || (stopReason && !cleanupAcknowledged)) return;
      let exists;
      try { exists = groupExists(); } catch(e) { finish(e); return; }
      if (!exists) finish(failure ?? (normalCompletion ? undefined : stopReason));
    };
    const stop = (reason) => {
      if (stopReason || settled) return;
      stopReason = reason;
      clearTimeout(timer);
      requestCleanup(child,graceMs).then(()=>{cleanupAcknowledged=true;check();}).catch(error=>{
        child.stdout?.destroy(); child.stderr?.destroy();
        finish(new ProcessCaptureError(error.message,'cleanup',false,reason));
      });
      poll = setInterval(check, 10);
      cleanupDeadline = setTimeout(() => {
        child.stdout?.destroy(); child.stderr?.destroy();
        finish(new ProcessCaptureError(`${reason.message}; process-group cleanup could not be confirmed`, 'cleanup', false, reason));
      }, graceMs + 5000);
      check();
    };
    const abort = () => stop(signal?.reason instanceof ProcessCaptureError
      ? signal.reason : new ProcessCaptureError('RunSpecimen call cancelled by the caller', 'cancelled'));
    onSpawn?.(child);
    child.stdout.on('data',chunk=>onData(chunk,'stdout')); child.stderr.on('data',chunk=>onData(chunk,'stderr'));
    child.on('error', e => {
      failure = e.code === 'ENOENT'
        ? new Error(`RunSpecimen CLI not found ('${command}'). Install it or set the plugin command config to its path.`) : e;
      if (!child.pid) finish(failure); else stop(failure);
    });
    child.on('message', message => {
      if(message?.type!=='command-exit' || settled || receivedCommandResult)return;
      receivedCommandResult=true;
      exitCode=message.code;
      onCommandResult?.(message);
      if(stopReason)return;
      normalCompletion=message.classification!=='leftovers';
      if(message.error)failure=message.error.code==='ENOENT'
        ? new Error(`RunSpecimen CLI not found ('${command}'). Install it or set the plugin command config to its path.`)
        : new Error(message.error.message);
      stop(new ProcessCaptureError(message.others
        ? 'RunSpecimen CLI exited leaving child processes; cleaned up its process group'
        : 'Command completed; cleaning up its supervisor', 'cleanup'));
    });
    child.on('close', code => {
      closed = true;
      if (settled) return;
      if (stopReason) {check(); return;}
      if(!receivedCommandResult)failure=new ProcessCaptureError("Supervisor exited without a command outcome acknowledgement", "cleanup", false);
      let exists;
      try {exists=groupExists();} catch(e) {finish(e);return;}
      if (exists) stop(new ProcessCaptureError('RunSpecimen CLI exited leaving child processes; cleaned up its process group', 'cleanup'));
      else finish(failure);
    });
    signal?.addEventListener('abort',abort,{once:true});
    timer = setTimeout(() => stop(new ProcessCaptureError(`RunSpecimen call exceeded its ${timeoutMs}ms budget`, 'timeout')),timeoutMs);
    if (signal?.aborted) abort();
  });
}
