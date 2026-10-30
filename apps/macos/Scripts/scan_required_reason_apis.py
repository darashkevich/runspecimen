#!/usr/bin/env python3
"""Inventory imported required-reason APIs in every shipped Mach-O of an app.

Accepts an .app or .xcarchive (Products/Applications/*.app; excludes dSYMs).
Reports capability imports against the closest bundled privacy manifest. This
does not prove runtime use, reason applicability, or App Store acceptance.
Keep the exact-category/reason gate as a separate check. No manifest is changed.
Apple catalog: https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacyaccessedapitypes/nsprivacyaccessedapitype
"""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import re
import subprocess
from pathlib import Path

MAGIC = {bytes.fromhex(x) for x in (
    'feedface','cefaedfe','feedfacf','cffaedfe',
    'cafebabe','bebafeca','cafebabf','bfbafeca',
)}
PATTERNS = {
    'FileTimestamp': re.compile(
        r'^_+(?:stat|stat64|fstat|fstat64|fstatat|lstat|lstat64|getattrlist|getattrlistbulk|getattrlistat|fgetattrlist)$'
        r'|_NSFile(?:Creation|Modification)Date$|_NSURL(?:CreationDate|ContentModificationDate|ContentAccessDate)Key$'
        r'|contentModificationDateKey|creationDateKey|fileModificationDate'),
    'DiskSpace': re.compile(
        r'^_+(?:statfs|statfs64|fstatfs|fstatfs64|statvfs|fstatvfs)$'
        r'|_NSURLVolume(?:AvailableCapacity(?:ForImportantUsage|ForOpportunisticUsage)?|TotalCapacity)Key$'
        r'|_NSFileSystem(?:Free)?Size$|volumeAvailableCapacity|volumeTotalCapacity'),
    'SystemBootTime': re.compile(r'^_+mach_absolute_time$|systemUptime'),
    'UserDefaults': re.compile(r'NSUserDefaults|UserDefaults'),
    'ActiveKeyboards': re.compile(r'activeInputModes'),
}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _imports(path: Path) -> str:
    result = subprocess.run(['xcrun','nm','-u',str(path)], capture_output=True,
                            text=True, timeout=10)
    if result.returncode:
        raise RuntimeError(f'nm failed for {path}: {result.stderr.strip()}')
    return result.stdout


def _manifest(binary: Path, app: Path):
    for parent in binary.parents:
        if not _inside(parent, app):
            break
        for candidate in (parent/'PrivacyInfo.xcprivacy',
                          parent/'Resources/PrivacyInfo.xcprivacy',
                          parent/'Contents/Resources/PrivacyInfo.xcprivacy'):
            if candidate.is_file():
                resolved = candidate.resolve()
                if not _inside(resolved, app):
                    raise ValueError(f'manifest resolves outside app: {candidate}')
                data = plistlib.loads(resolved.read_bytes())
                entries = data.get('NSPrivacyAccessedAPITypes', [])
                declarations = {}
                for entry in entries:
                    category = entry['NSPrivacyAccessedAPIType'].removeprefix('NSPrivacyAccessedAPICategory')
                    if category in declarations:
                        raise ValueError(f'duplicate privacy category {category}: {candidate}')
                    declarations[category] = entry.get('NSPrivacyAccessedAPITypeReasons', [])
                return candidate, declarations
    return None, {}


def scan(source: Path, *, read_symbols=None) -> dict:
    source = Path(source).resolve()
    if not source.is_dir():
        raise ValueError(f'not a built app or archive: {source}')
    if source.suffix == '.xcarchive':
        apps = sorted((source/'Products/Applications').glob('*.app'))
    elif source.suffix == '.app':
        apps = [source]
    else:
        raise ValueError('pass a built .app or .xcarchive')
    if not apps:
        raise ValueError('archive contains no application bundles')
    read_symbols = read_symbols or _imports
    rows, manifests, undeclared = [], {}, set()
    for app in apps:
        app = app.resolve()
        if not _inside(app, source):
            raise ValueError(f'app resolves outside input: {app}')
        seen = set()
        for path in sorted(app.rglob('*')):
            resolved = path.resolve()
            if not _inside(resolved, app):
                raise ValueError(f'file resolves outside app: {path}')
            if not path.is_file() or resolved in seen:
                continue
            with path.open('rb') as stream:
                magic = stream.read(4)
            if magic not in MAGIC:
                continue
            seen.add(resolved)
            text = read_symbols(path)
            symbols = sorted({line.split()[-1] for line in text.splitlines() if line.split()})
            hits = {category: [s for s in symbols if pattern.search(s)]
                    for category, pattern in PATTERNS.items()}
            hits = {category: values for category, values in hits.items() if values}
            manifest, declarations = _manifest(path, app)
            manifest_name = str(manifest.relative_to(source)) if manifest else None
            if manifest:
                manifests[manifest_name] = {
                    'sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
                    'declarations':declarations,
                }
            missing = sorted(category for category in hits if not declarations.get(category))
            undeclared.update(missing)
            rows.append({
                'binary':str(path.relative_to(source)),
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'manifest':manifest_name, 'imported_categories':hits,
                'undeclared_categories':missing,
            })
    if not rows:
        raise ValueError('no shipped Mach-O binaries found')
    return {
        'input':str(source), 'scope':'All actual Mach-O files in shipped app bundles; archive dSYMs excluded.',
        'manifests':manifests, 'binaries':rows,
        'undeclared_categories':sorted(undeclared),
        'limits':'Imported capability is not proof of execution, valid reason applicability or Apple acceptance. Dynamic selector use and catalog changes require review. No accepted declaration is changed.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--check', action='store_true',
                        help='exit nonzero when a shipped required-reason API category is undeclared')
    args = parser.parse_args()
    result = scan(args.input)
    print(json.dumps(result, indent=2))
    if args.check and result['undeclared_categories']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
