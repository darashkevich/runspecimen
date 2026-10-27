"""Smoke-only concurrent load: baseline also passes; deterministic barrier tests prove the fix. Never retry failures away."""
from __future__ import annotations
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import time

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--iterations',type=int,default=100)
    parser.add_argument('--test',default='tests.test_launch_faults.LaunchFaultTests.test_killing_the_wrapper_drops_the_lease_without_success')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not (1<=args.workers<=16 and 1<=args.iterations<=1000):parser.error('workers 1..16; iterations 1..1000')
    repo=args.repo.resolve();started=time.monotonic()
    def worker(number):
        env=os.environ.copy();env['PYTHONPATH']=str(repo/'src')
        failures=[]
        for iteration in range(args.iterations):
            try:
                result=subprocess.run([sys.executable,'-m','unittest',args.test],cwd=repo,env=env,
                    capture_output=True,text=True,timeout=45)
                if result.returncode:
                    failures.append({'worker':number,'iteration':iteration,'returncode':result.returncode,
                        'stdout':result.stdout,'stderr':result.stderr})
            except subprocess.TimeoutExpired as error:
                failures.append({'worker':number,'iteration':iteration,'timeout':str(error)})
        return failures
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        failures=[failure for group in pool.map(worker,range(args.workers)) for failure in group]
    report={'platform':sys.platform,'python':sys.version,'test':args.test,'repo':str(repo),
        'workers':args.workers,'iterations':args.iterations,'runs':args.workers*args.iterations,
        'seconds':time.monotonic()-started,'failures':failures}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"{report['runs']} runs, {len(failures)} failures; {args.output}")
    return bool(failures)

if __name__=='__main__':raise SystemExit(main())
