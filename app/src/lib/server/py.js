import { spawn } from 'node:child_process';

/** Run a project Python script through uv. Script must print one JSON object to stdout. */
export function runPy(script, { args = [], input = '', timeout = 120_000 } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn('uv', ['run', '--quiet', script, ...args], { cwd: process.cwd() });
    let out = '', err = '';
    const timer = setTimeout(() => { child.kill('SIGKILL'); reject(new Error(`${script} timed out`)); }, timeout);
    child.stdout.on('data', (d) => (out += d));
    child.stderr.on('data', (d) => (err = (err + d).slice(-4000)));
    child.on('error', (e) => { clearTimeout(timer); reject(new Error(`Cannot start uv: ${e.message}`)); });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) return reject(new Error(err.trim().split('\n').pop() || `${script} exited ${code}`));
      try { resolve(JSON.parse(out)); } catch { reject(new Error(`Bad output from ${script}`)); }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(input);
  });
}
