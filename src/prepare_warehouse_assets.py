"""Download NVIDIA USD dependencies, preserving relative paths and textures.
Run using Isaac python.sh (OpenUSD bindings required). Does not start SimulationApp.
"""
import concurrent.futures
import json
import os
from pathlib import Path
from project_paths import PROJECT_ROOT, CONFIG_DIR, ASSETS_DIR
import re
import subprocess
import sys
import urllib.parse
from pxr import Sdf

HOST = 'https://omniverse-content-production.s3-us-west-2.amazonaws.com'
ROOT = HOST + '/Assets'
ISAAC = ROOT + '/Isaac/6.1'
CONFIG = CONFIG_DIR/'warehouse_assets_requested.json'
REQUESTED = json.loads(CONFIG.read_text())
ASSETS = REQUESTED['remote']

CACHE = ASSETS_DIR / 'nvidia_cache'
OFFLINE = '--offline' in sys.argv
BUILTINS = ('OmniPBR.mdl', 'OmniGlass.mdl', 'OmniSurface.mdl')


def local(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc != urllib.parse.urlparse(HOST).netloc or not parsed.path.startswith('/Assets/'):
        raise ValueError('Outside NVIDIA asset tree: ' + url)
    p = CACHE / parsed.path.lstrip('/')
    if not p.resolve().is_relative_to(CACHE.resolve()):
        raise ValueError('Unsafe asset path: ' + url)
    return p


def fetch(url):
    p = local(url)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + '.part')
        # Large standalone models: parallel byte ranges, each chunk is resumable.
        known_sizes = {'ConveyorBelt_A08.usd': 36908591, 'forklift.usd': 19359304}
        total = known_sizes.get(p.name)
        if total is None:
            headers = subprocess.run(['curl','--head','--location','--silent','--show-error',
                                      '--fail','--connect-timeout','10','--max-time','25',url],
                                     check=True, capture_output=True, text=True, timeout=30).stdout
            lengths = re.findall(r'(?im)^content-length:\s*(\d+)', headers)
            length = int(lengths[-1]) if lengths else 0
            total = length if length > 2*1024*1024 else None
        if total:
            chunk_size = 1024 * 1024
            chunks = []
            def piece(start):
                end = min(start + chunk_size, total) - 1
                part = p.with_name(p.name + f'.chunk.{start}')
                if not part.exists() or part.stat().st_size != end-start+1:
                    subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                                    '--connect-timeout', '10', '--max-time', '120', '--retry', '2',
                                    '--range', f'{start}-{end}', '--output', str(part), url],
                                   check=True, timeout=370)
                if part.stat().st_size != end-start+1:
                    raise RuntimeError('Server did not return requested byte range: ' + url)
                return part
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as workers:
                chunks = list(workers.map(piece, range(0,total,chunk_size)))
            with tmp.open('wb') as out:
                for part in chunks:
                    out.write(part.read_bytes())
        else:
            subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                            '--connect-timeout', '10', '--max-time', '120',
                            '--continue-at', '-', '--output', str(tmp), url], check=True, timeout=125)
        tmp.replace(p)
    deps = []
    if p.suffix.lower() in ('.usd', '.usda', '.usdc'):
        layer = Sdf.Layer.FindOrOpen(str(p))
        if layer is None:
            raise RuntimeError('Cannot open USD: ' + str(p))
        text = layer.ExportToString()
        def rewrite(match):
            v = match.group(1)
            if not v or v in BUILTINS or v.startswith('anon:'):
                return match.group(0)
            remote = urllib.parse.urljoin(url, v)
            ext = Path(urllib.parse.urlparse(remote).path).suffix.lower()
            if ext in ('.usd', '.usda', '.usdc'):
                deps.append(remote)
                return match.group(0)
            if not ext:
                return match.group(0)
            if OFFLINE:
                deps.append(remote)
                return '@' + os.path.relpath(local(remote), p.parent) + '@'
            return '@' + remote + '@'
        updated = re.sub(r'@([^@\r\n]*)@', rewrite, text)
        if updated != text:
            layer.ImportFromString(updated)
            layer.Save(force=True)
    return deps


def local_dependencies(path, seen=None):
    seen = set() if seen is None else seen
    path = Path(path).resolve()
    if path in seen:
        return []
    seen.add(path)
    if not path.exists():
        return [str(path)]
    layer = Sdf.Layer.FindOrOpen(str(path))
    if layer is None:
        return [str(path) + ' (invalid USD)']
    missing = []
    for dep in layer.GetExternalReferences():
        if '://' in dep:
            missing.append(dep + ' (remote dependency, not cached)')
        elif Path(dep).suffix.lower() in ('.usd', '.usda', '.usdc'):
            missing.extend(local_dependencies(path.parent / dep, seen))
    return sorted(set(missing))


def main():
    pending, seen, errors = set(ASSETS.values()), set(), {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        while pending:
            batch = pending - seen
            if not batch:
                break
            seen.update(batch)
            pending = set()
            jobs = {pool.submit(fetch, url): url for url in batch}
            for job in concurrent.futures.as_completed(jobs):
                url = jobs[job]
                try:
                    pending.update(job.result())
                    print('OK', urllib.parse.urlparse(url).path, flush=True)
                except Exception as exc:
                    errors[url] = str(exc)
                    print('FAIL', url, str(exc), flush=True)
    resolved = {k: str(local(v)) for k, v in ASSETS.items()}
    pending_local = {}
    for kind, entry in REQUESTED.get('local', {}).items():
        path = Path(entry).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        missing = local_dependencies(path)
        if missing:
            pending_local[kind] = {'entry': str(path), 'missing': missing,
                                   'recovered_from_source': kind in resolved}
        else:
            resolved[kind] = str(path)
    report = {'assets': resolved, 'pending_local': pending_local, 'errors': errors,
              'material_mode': 'offline' if OFFLINE else 'NVIDIA streaming'}
    out = CACHE / 'warehouse_assets.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print('MANIFEST', out, 'errors:', len(errors))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
