"""Select an available iPhone on the installed Simulator SDK's runtime."""
import json
import sys

def select(data, sdk):
    prefix='com.apple.CoreSimulator.SimRuntime.iOS-'+sdk.replace('.', '-')
    for runtime, devices in data.get('devices',{}).items():
        if runtime != prefix and not runtime.startswith(prefix+'-'): continue
        for device in devices:
            if device.get('isAvailable') and 'iPhone' in device.get('name',''):
                return device['udid']
    raise ValueError(f'No available iPhone runtime matching installed SDK {sdk}')

if __name__=='__main__':
    print(select(json.load(sys.stdin), sys.argv[1]))
