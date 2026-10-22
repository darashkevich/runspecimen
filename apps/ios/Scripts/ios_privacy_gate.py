"""Assert the shipped iPhone manifest and audit linked required-reason API symbols.

This is a conservative linked-symbol gate, not proof that indirect Foundation
calls or future Apple API-list changes require no further archive review.
Apple list: https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacyaccessedapitypes/nsprivacyaccessedapitype
"""
import argparse
import hashlib
import json
import plistlib
import re
import subprocess
from pathlib import Path

CATEGORIES={
    'UserDefaults':r'UserDefaults',
    'FileTimestamp':r'(?m)\b_(?:stat|stat64|fstat|fstat64|fstatat|lstat|lstat64|getattrlist|getattrlistbulk|fgetattrlist|getattrlistat)\b|contentModificationDateKey|creationDateKey|fileModificationDate|^(?:creationDate|modificationDate)$',
    'SystemBootTime':r'\b_mach_absolute_time\b|systemUptime',
    'DiskSpace':r'\b_(?:statfs|statfs64|fstatfs|fstatfs64|statvfs|fstatvfs)\b|volumeAvailableCapacity|volumeTotalCapacity|systemFreeSize|systemSize',
    'ActiveKeyboards':r'activeInputModes',
}

def audit(app, symbols):
    manifest=app/'PrivacyInfo.xcprivacy'
    if not manifest.is_file():
        raise ValueError('Release bundle privacy manifest is missing')
    data=plistlib.loads(manifest.read_bytes())
    entries={entry['NSPrivacyAccessedAPIType']:entry.get('NSPrivacyAccessedAPITypeReasons',[])
             for entry in data.get('NSPrivacyAccessedAPITypes',[])}
    if 'CA92.1' not in entries.get('NSPrivacyAccessedAPICategoryUserDefaults',[]):
        raise ValueError('Release manifest must declare app-only UserDefaults CA92.1')
    found={}
    for binary,text in symbols.items():
        for category,pattern in CATEGORIES.items():
            hits=sorted(set(re.findall(pattern,text)))
            if not hits:continue
            found.setdefault(category,{})[binary]=hits
            if not entries.get('NSPrivacyAccessedAPICategory'+category):
                raise ValueError(f'{binary}: linked {category} API has no declared reason: {hits}')
    return {'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
            'binaries':sorted(symbols),'linked_categories':found,
            'limits':'Symbol audit does not prove absence of indirect API use or App Store acceptance.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app',type=Path)
    args=parser.parse_args()
    app=args.app
    info=plistlib.loads((app/'Info.plist').read_bytes())
    executable=app/info['CFBundleExecutable']
    if not executable.is_file():raise ValueError('Release app executable is missing')
    # Scan every actual Mach-O, including nested executables and libraries.
    symbols={}
    for path in sorted(app.rglob('*')):
        if not path.is_file():continue
        with path.open('rb') as stream:magic=stream.read(4)
        if magic not in {bytes.fromhex(x) for x in ['feedface','cefaedfe','feedfacf','cffaedfe','cafebabe','bebafeca','cafebabf','bfbafeca']}:continue
        nm=subprocess.run(['xcrun','nm','-u',str(path)],check=True,capture_output=True,text=True)
        strings=subprocess.run(['/usr/bin/strings','-a',str(path)],check=True,capture_output=True,text=True)
        # Only exact Objective-C property selectors augment the symbol audit.
        selectors='\n'.join(line for line in strings.stdout.splitlines() if line in {
            'creationDate','modificationDate','fileModificationDate','contentModificationDateKey','creationDateKey',
            'systemUptime','activeInputModes','volumeAvailableCapacity','volumeAvailableCapacityKey',
            'volumeAvailableCapacityForImportantUsageKey','volumeAvailableCapacityForOpportunisticUsageKey',
            'volumeTotalCapacity','volumeTotalCapacityKey','systemFreeSize','systemSize'})
        symbols[str(path.relative_to(app))]=nm.stdout+'\n'+selectors
    if str(executable.relative_to(app)) not in symbols:raise ValueError('No linked app Mach-O was audited')
    print(json.dumps(audit(app,symbols),indent=2))

if __name__=='__main__':main()
