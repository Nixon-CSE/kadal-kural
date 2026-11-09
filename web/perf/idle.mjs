// Idle main-thread cost per page on the real GPU: CDP Performance metrics over a 5 s idle window.
// node --experimental-websocket web/perf/idle.mjs / /desk /insights   (BASE=http://localhost:8000)
import { spawn } from "node:child_process"; import { mkdtempSync } from "node:fs"; import { tmpdir } from "node:os"; import { join } from "node:path";
const paths = process.argv.slice(2);
const port = 9600 + Math.floor(Math.random()*90);
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", ["--headless=new","--use-angle=metal","--enable-gpu","--ignore-gpu-blocklist",`--remote-debugging-port=${port}`,`--user-data-dir=${mkdtempSync(join(tmpdir(),"kkperf-"))}`,"about:blank"],{stdio:"ignore"});
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms)); let t;
for (let i=0;i<50&&!t;i++){try{t=(await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(x=>x.type==="page")}catch{await sleep(200)}}
const ws=new WebSocket(t.webSocketDebuggerUrl); await new Promise(r=>ws.onopen=r); let id=0; const p=new Map();
ws.onmessage=m=>{const d=JSON.parse(m.data); if(p.has(d.id)){p.get(d.id)(d.result);p.delete(d.id)}};
const send=(method,params={})=>new Promise(r=>{const i=++id;p.set(i,r);ws.send(JSON.stringify({id:i,method,params}))});
await send("Emulation.setDeviceMetricsOverride",{width:1440,height:900,deviceScaleFactor:1,mobile:false});
await send("Emulation.setFocusEmulationEnabled",{enabled:true});
await send("Performance.enable");
const get=async()=>Object.fromEntries((await send("Performance.getMetrics")).metrics.map(m=>[m.name,m.value]));
for (const path of paths) {
  await send("Page.navigate",{url:(process.env.BASE || "http://localhost:8000")+path}); await sleep(6000);
  const a=await get(); await sleep(5000); const b=await get();
  const d=(k)=>((b[k]-a[k])*1000).toFixed(0);
  console.log(`${path.padEnd(10)} busy ${d("TaskDuration").padStart(5)} ms/5s  script ${d("ScriptDuration").padStart(5)}  style ${d("RecalcStyleDuration").padStart(4)}  layout ${d("LayoutDuration").padStart(4)}  nodes ${b.Nodes}`);
}
chrome.kill(); process.exit(0);
