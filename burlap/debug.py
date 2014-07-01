import re

from fabric.api import (
    env,
    local,
    put as _put,
    require,
    #run as _run,
    run,
    settings,
    sudo,
    cd,
    task,
)

@task
def list_env():
    """
    Displays a list of environment key/value pairs.
    """
    for k,v in env.iteritems():
        print k,v

def list_to_str_or_unknown(lst):
    if len(lst):
        return ', '.join(map(str, lst))
    return 'unknown'

@task
def list_server_specs(cpu=1, memory=1, hdd=1):
    """
    Displays a list of common servers characteristics, like number
    of CPU cores, amount of memory and hard drive capacity.
    """
    
    cpu = int(cpu)
    memory = int(memory)
    hdd=  int(hdd)
    
    # CPU
    if cpu:
        cmd = 'cat /proc/cpuinfo | grep -i "model name"'
        ret = run(cmd)
        matches = map(str.strip, re.findall('model name\s+:\s*([^\n]+)', ret, re.DOTALL|re.I))
        cores = {}
        for match in matches:
            cores.setdefault(match, 0)
            cores[match] += 1
    
    # Memory
    if memory:
        cmd = 'dmidecode --type 17'
        ret = sudo(cmd)
        #print repr(ret)
        matches = re.findall('Memory\s+Device\r\n(.*?)(?:\r\n\r\n|$)', ret, flags=re.DOTALL|re.I)
        #print len(matches)
        #print matches[0]
        memory_slot_dicts = []
        for match in matches:
            attrs = dict([(_a.strip(), _b.strip()) for _a, _b in re.findall('^([^:]+):\s+(.*)$', match, flags=re.MULTILINE)])
            #print attrs
            memory_slot_dicts.append(attrs)
        total_memory_gb = 0
        total_slots_filled = 0
        total_slots = len(memory_slot_dicts)
        memory_types = set()
        memory_forms = set()
        memory_speeds = set()
        for memory_dict in memory_slot_dicts:
            try:
                size = int(round(float(re.findall('([0-9]+)\s+MB', memory_dict['Size'])[0])/1024.))
                #print size
                total_memory_gb += size
                total_slots_filled += 1
            except IndexError:
                pass
            _v = memory_dict['Type']
            if _v != 'Unknown':
                memory_types.add(_v)
            _v = memory_dict['Form Factor']
            if _v != 'Unknown':
                memory_forms.add(_v)
            _v = memory_dict['Speed']
            if _v != 'Unknown':
                memory_speeds.add(_v)
    
    # Storage
    if hdd:
        #cmd = 'ls /dev/*d* | grep "/dev/[a-z]+d[a-z]$"'
        cmd = 'find /dev -maxdepth 1 | grep -E "/dev/[a-z]+d[a-z]$"'
        devices = map(str.strip, run(cmd).split('\n'))
        total_drives = len(devices)
        total_physical_storage_gb = 0
        total_logical_storage_gb = 0
        drive_transports = set()
        for device in devices:
            cmd = 'udisks --show-info %s |grep -i "  size:"' % (device)
            ret = run(cmd)
            size_bytes = float(re.findall('size:\s*([0-9]+)', ret)[0].strip())
            size_gb = int(round(size_bytes/1024/1024/1024))
            #print device, size_gb
            total_physical_storage_gb += size_gb
            
            with settings(warn_only=True):
                cmd = 'hdparm -I %s|grep -i "Transport:"' % device
                ret = sudo(cmd)
                if ret and not ret.return_code:
#                    print dir(ret)
#                    print ret.__dict__.keys()
                    drive_transports.add(ret.split('Transport:')[-1].strip())
                
        cmd = "df | grep '^/dev/[mhs]d*' | awk '{s+=$2} END {print s/1048576}'"
        ret = run(cmd)
        total_logical_storage_gb = float(ret)
    
    if cpu:
        print '-'*80
        print 'CPU'
        print '-'*80
        type_str = ', '.join(['%s x %i' % (_type, _count) for _type, _count in cores.items()])
        print 'Cores: %i' % sum(cores.values())
        print 'Types: %s' % type_str
    
    if memory:
        print '-'*80
        print 'MEMORY'
        print '-'*80
        print 'Total: %s GB' % total_memory_gb
        print 'Type: %s' % list_to_str_or_unknown(memory_types)
        print 'Form: %s' % list_to_str_or_unknown(memory_forms)
        print 'Speed: %s' % list_to_str_or_unknown(memory_speeds)
        print 'Slots: %i (%i filled, %i empty)' % (total_slots, total_slots_filled, total_slots - total_slots_filled)
    
    if hdd:
        print '-'*80
        print 'STORAGE'
        print '-'*80
        print 'Total physical drives: %i' % total_drives
        print 'Total physical storage: %s GB' % total_physical_storage_gb
        print 'Total logical storage: %s GB' % total_logical_storage_gb
        print 'Types: %s' % list_to_str_or_unknown(drive_transports)
        