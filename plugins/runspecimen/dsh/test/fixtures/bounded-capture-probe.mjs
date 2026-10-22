const {runCli}=await import(process.argv[2]);
const r=await runCli({command:process.execPath,argv:['-e',"const fs=require('node:fs');const chunk=Buffer.alloc(65536,120);for(let i=0;i<1024;i++)fs.writeSync(1,chunk);"],timeoutMs:10000,maxOutputBytes:256});
console.log(JSON.stringify({exitCode:r.exitCode,truncated:r.truncated,bytes:Buffer.byteLength(r.text)}));
