import { spawn } from 'node:child_process';

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

/** Retry only while the original ChildProcess still pins its leader PID.
 * Once reaped, a numeric PGID alone cannot prove identity; never signal it.
 */
export async function retryOwnedGroup(child, graceMs=250) {
  const exists=()=>{
    try {process.kill(-child.pid,0);return true;}
    catch(e){if(e.code==='ESRCH')return false;if(e.code==='EPERM')return true;throw new ProcessCaptureError(`Cleanup retry inspection failed: ${e.message}`,'cleanup',false,e);}
  };
  const signal=sig=>{
    if(child.exitCode!==null || child.signalCode!==null)
      throw new ProcessCaptureError('Cleanup unresolved: original leader exited; refusing a possibly reused process-group ID','cleanup',false);
    try {process.kill(-child.pid,sig);} catch(e) {if(e.code!=='ESRCH')throw new ProcessCaptureError(`Cleanup retry ${sig} failed: ${e.message}`,'cleanup',false,e);}
  };
  if(!exists())return;
  signal('SIGTERM');
  await new Promise((resolve,reject)=>{
    let poll,grace,deadline;
    const finish=error=>{clearInterval(poll);clearTimeout(grace);clearTimeout(deadline);error?reject(error):resolve();};
    const check=()=>{try{if(!exists())finish();}catch(e){finish(new ProcessCaptureError(e.message,'cleanup',false,e));}};
    poll=setInterval(check,10);
    grace=setTimeout(()=>{try{if(!exists()){finish();return;}signal('SIGKILL');check();}catch(e){finish(e);}},graceMs);
    deadline=setTimeout(()=>finish(new ProcessCaptureError('Cleanup retry could not confirm process-group death','cleanup',false)),graceMs+5000);
    check();
  });
}

/** Own a POSIX process group; do not finish cancellation before cleanup. */
export function captureProcess({command, argv, cwd, signal, timeoutMs, onData, onSpawn, graceMs=250}) {
  if (process.platform === 'win32') throw new Error('This plugin requires macOS or Linux process-group cleanup; Windows is not supported.');
  if (signal?.aborted) return Promise.reject(new Error('RunSpecimen call cancelled by the caller; nothing was started'));
  return new Promise((resolve, reject) => {
    let settled = false, closed = false, exitCode, stopReason, failure;
    let timer, grace, poll, cleanupDeadline;
    const child = spawn(command, argv, {cwd, detached:true, stdio:['ignore','pipe','pipe'],
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
    const kill = (sig) => {
      if (!child.pid) return;
      try { process.kill(-child.pid, sig); }
      catch (e) { if (e.code !== 'ESRCH') failure = new ProcessCaptureError(`Process-group signal ${sig} failed: ${e.message}`, 'cleanup', false, e); }
    };
    const finish = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer); clearTimeout(grace); clearTimeout(cleanupDeadline); clearInterval(poll);
      signal?.removeEventListener('abort', abort);
      if (error) reject(error); else resolve(exitCode ?? -1);
    };
    const check = () => {
      if (!closed) return;
      let exists;
      try { exists = groupExists(); } catch(e) { finish(e); return; }
      if (!exists) finish(failure ?? stopReason);
    };
    const stop = (reason) => {
      if (stopReason || settled) return;
      stopReason = reason;
      clearTimeout(timer);
      kill('SIGTERM');
      // Always retain ownership through escalation, even if the direct child
      // exits first and leaves a descendant whose stdio is already closed.
      grace = setTimeout(() => {kill('SIGKILL'); check();}, graceMs);
      poll = setInterval(check, 10);
      cleanupDeadline = setTimeout(() => {
        kill('SIGKILL');
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
    child.on('close', code => {
      closed = true; exitCode = code;
      if (settled) return;
      if (stopReason) {check(); return;}
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
