// Keep the persistent Jarvis service alive when opening the desktop.
const {spawn} = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const install = path.join(process.env.LOCALAPPDATA, 'OpenJarvis');
async function healthy() {
  try {
    const response = await fetch('http://127.0.0.1:8000/health',
      {signal: AbortSignal.timeout(2000)});
    return response.ok && (await response.json()).status === 'ok';
  } catch { return false; }
}
async function launch() {
  if (!await healthy()) {
    const script = path.join(process.env.USERPROFILE, '.openjarvis', 'start-jarvis.ps1');
    const stack = spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass',
      '-File', script], {windowsHide:true, detached:true, stdio:'ignore'});
    stack.on('error', report);
    stack.unref();
    for (let attempt = 0; attempt < 60 && !await healthy(); attempt++)
      await new Promise(resolve => setTimeout(resolve, 1000));
    if (!await healthy()) throw new Error('Jarvis backend did not become healthy. See .openjarvis/logs.');
  }
  const child = spawn(path.join(install, 'openjarvis-desktop.exe'), [],
    {cwd:install, detached:true, stdio:'ignore', windowsHide:false});
  child.on('error', report);
  child.unref();
}
function report(error) {
  fs.writeFileSync(path.join(install, 'launcher-error.log'), String(error));
  process.exitCode = 1;
}
launch().catch(report);
