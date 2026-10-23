"""Optional legacy diagnostic CLI; not part of the frozen research workflow.

Retained for compatibility pending retirement in a future breaking release.
Requires a user-supplied configuration because no network-triggering sample
configuration is bundled with the public study package.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import yaml
from .provider import fetch_daily
from .quality import validate_bars

def main():
    parser = argparse.ArgumentParser(description='Legacy optional data probe; requires an explicit YAML config and is outside the frozen research workflow.')
    parser.add_argument('--config', required=True, help='user-supplied YAML configuration; no default is bundled')
    parser.add_argument('--output', default='outputs')
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding='utf-8'))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for symbol in config['symbols']:
        for adj in config['adjustments']:
            mode = adj or 'raw'
            entry = {'symbol':symbol, 'adjust':mode, 'status':'error'}
            try:
                df = fetch_daily(symbol, config['start_date'], config['end_date'], adj)
                report = validate_bars(df)
                entry.update(report)
                entry['status'] = 'ok' if report['passed'] else 'quality_warning'
                if not df.empty:
                    path = output / f'{symbol}_{mode}.csv'
                    df.to_csv(path, index=False, encoding='utf-8')
                    entry['file'] = str(path)
                    entry['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            except Exception as exc:
                entry['error'] = f'{type(exc).__name__}: {exc}'
            rows.append(entry)
            print(f"{symbol} {mode}: {entry['status']}", flush=True)
            time.sleep(float(config.get('request_pause_seconds', 1)))
    manifest = {'run_id':run_id, 'utc_created':datetime.now(timezone.utc).isoformat(),
                'python':sys.version.split()[0], 'platform':platform.platform(),
                'config':config, 'results':rows}
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    report = ['# Data Probe Report','',f'Run: {run_id} (UTC)','',
              '| Symbol | Adjustment | Rows | Status | Findings / Error |', '|---|---|---:|---|---|']
    for r in rows:
        details = '; '.join(r.get('findings', [])) or r.get('error','—')
        report.append(f"| {r['symbol']} | {r['adjust']} | {r.get('rows','—')} | {r['status']} | {details.replace('|','/')} |")
    report += ['', '## Interpretation',
               '- This is a convenience-sample probe, not a complete historical-universe or survivorship-bias audit.',
               '- Calendar gaps alone do not establish missing observations: holidays and suspensions require an exchange calendar and suspension history.',
               '- Adjusted prices are provider-defined; compare adjustment conventions before using them in factor research.',
               '- Historical ST flags, delisted constituents, point-in-time availability, and tradeability remain UNVERIFIED.',
               '- A successful download is not permission to redistribute the underlying data.']
    (output/'report.md').write_text('\n'.join(report)+'\n', encoding='utf-8')
    print(f'Wrote {output / "report.md"} and manifest.json')

if __name__ == '__main__': main()
