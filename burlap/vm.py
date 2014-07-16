import os
import sys
import datetime
import socket
import pprint
import time
import yaml

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
from fabric.contrib import files

from burlap import common
from burlap.common import run, put

try:
    import boto
    import boto.ec2
except ImportError:
    boto = None

EC2 = 'ec2'

env.vm_name_tag = 'Name'
env.vm_group_tag = 'Group'
env.vm_release_tag = 'Release'

env.vm_type = None

# If a name is not given, one will be auto-generated based on this pattern.
env.vm_name_template = 'web{index}'

# A release tag given to the instance when created to distinquish it from
# future upgrades to the same instance name.
env.vm_release = None

env.vm_ec2_account_id = None
# https://help.ubuntu.com/community/EC2StartersGuide#Official_Ubuntu_Cloud_Guest_Amazon_Machine_Images_.28AMIs.29
env.vm_ec2_ami = None # e.g. 'ami-a29943cb'
env.vm_ec2_instance_type = None # e.g. 'm1.small'
env.vm_ec2_ebs = None
env.vm_ec2_region = None # e.g. 'us-east-1'
env.vm_ec2_zone = None # e.g. 'us-east-1b'
env.vm_ec2_available_security_groups = {} # {(name,desc):[(protocol, port, port, ip_range)]
env.vm_ec2_selected_security_groups = []
env.vm_ec2_aws_access_key_id = None
env.vm_ec2_aws_secret_access_key = None
env.vm_ec2_volume = '/dev/sdh1'
env.vm_ec2_keypair_name = None
env.vm_ec2_use_elastic_ip = False

def retrieve_ec2_hosts():
    for name, data in list_instances(show=0).iteritems():
        yield data.public_dns_name

env.hosts_retrievers['ec2'] = retrieve_ec2_hosts

def translate_ec2_hostname(hostname):
    for name, data in list_instances(show=0).iteritems():
        if name == hostname:
            return data.public_dns_name

env.hostname_translators['ec2'] = translate_ec2_hostname

def get_ec2_connection():
#    assert 'AWS_CREDENTIAL_FILE' in os.environ, \
#        'AWS environment variables not set.'
#    return boto.connect_ec2()
#    print env.vm_ec2_aws_access_key_id
#    print env.vm_ec2_aws_secret_access_key
    conn = boto.ec2.connect_to_region(
        #env.vm_ec2_zone,
        env.vm_ec2_region,
        aws_access_key_id=env.vm_ec2_aws_access_key_id,
        aws_secret_access_key=env.vm_ec2_aws_secret_access_key,
    )
#    print 'conn:',conn
    return conn

@task
def test():
    from burlap.common import shelf
    #conn = get_ec2_connection()
    #print conn
#    instances = get_all_ec2_instances()
#    print instances
#    shelf.set('vm_ips', [1,2,3])
#    shelf.set('vm_xyz', [123])

def get_all_ec2_instances(instance_ids=None):
    conn = get_ec2_connection()
    return sum(map(lambda r: r.instances, conn.get_all_instances(instance_ids=instance_ids)), [])

def get_all_running_ec2_instances():
    instances = filter(lambda i: i.state == 'running', get_all_ec2_instances())
    instances.reverse()
    return instances

@task
def list_instances(show=1, name=None, group=None, release=None, except_release=None):
    """
    Retrieves all virtual machines instances in the current environment.
    """
    require('vm_type', 'vm_group')
    #print 'env.vm_typeL:',env.vm_type
    assert env.vm_type, 'No VM type specified.'
    #assert env.vm_group, 'No VM group specified.'
    env.vm_type = (env.vm_type or '').lower()
    _name = name
    _group = group
    _release = release
    data = type(env)()
    if env.vm_type == EC2:
        for instance in get_all_running_ec2_instances():
            name = instance.tags.get(env.vm_name_tag)
            group = instance.tags.get(env.vm_group_tag)
            release = instance.tags.get(env.vm_release_tag)
#            print 'name:',name
#            print 'group:',group,env.vm_group
            if env.vm_group and group and env.vm_group != group:
                print('skipping vm_group:',env.vm_group, group)
                continue
            if _group and group and group != _group:
                print('skipping direct group:',_group, group)
                continue
            if _name and name and name != _name:
                print('skipping direct name:',_name,name)
                continue
            if _release and release and release != _release:
                print('skipping direct release:',_release,release)
                continue
            if except_release and release == except_release:
                continue
            data.setdefault(name, type(env)())
            data[name]['id'] = instance.id
            data[name]['public_dns_name'] = instance.public_dns_name
            data[name]['ip'] = socket.gethostbyname(instance.public_dns_name)
        if int(show):
            pprint.pprint(data, indent=4)
        return data
    elif env.vm_type == KVM:
        #virsh list
        pass
    else:
        raise NotImplementedError

#class SecurityGroup(object):
#    
#    def get_or_create(cls, name):
#        pass

#sg = SecurityGroup()
#get_or_create = task(sg.get_or_create)

@task
def get_or_create_ec2_security_groups(names=None, verbose=1):
    """
    Creates a security group opening 22, 80 and 443
    """
    verbose = int(verbose)
    
    if verbose:
        print('Creating EC2 security groups...')
    
    conn = get_ec2_connection()
    
    if isinstance(names, basestring):
        names = names.split(',')
    names = names or env.vm_ec2_selected_security_groups
    
    ret = []
    for name in names:
        try:
            group = conn.get_all_security_groups(groupnames=[name])[0]
        except boto.exception.EC2ResponseError:
            group = get_ec2_connection().create_security_group(
                name,
                name,
            )
        ret.append(group)
        
        # Find existing rules.
        actual_sets = set()
        for rule in list(group.rules):
            ip_protocol = rule.ip_protocol
            from_port = rule.from_port
            to_port = rule.to_port
            for cidr_ip in rule.grants:
                #print('Revoking:', ip_protocol, from_port, to_port, cidr_ip)
                #group.revoke(ip_protocol, from_port, to_port, cidr_ip)
                rule_groups = ((rule.groups and rule.groups.split(',')) or [None])
                for src_group in rule_groups:
                    actual_sets.add((ip_protocol, from_port, to_port, str(cidr_ip), src_group))
        
        # Find actual rules.
        expected_sets = set()
        for authorization in env.vm_ec2_available_security_groups.get(name, []):
            ip_protocol, from_port, to_port, cidr_ip, src_group = authorization
            expected_sets.add((ip_protocol, str(from_port), str(to_port), cidr_ip, src_group))
            
        # Calculate differences.
        del_sets = actual_sets.difference(expected_sets)
        add_sets = expected_sets.difference(actual_sets)
#        print 'actual:',actual_sets
#        print 'expected:',expected_sets
#        print 'del:',del_sets
#        print 'add:',add_sets
        
        # Revoke deleted.
        for auth in del_sets:
            group.revoke(*auth)
        
        # Create fresh rules.
        for auth in add_sets:
            group.authorize(*auth)
            
    return ret

@task
def get_or_create_ec2_key_pair(name=None, verbose=1):
    """
    Creates and saves an EC2 key pair to a local PEM file.
    """
    verbose = int(verbose)
    name = name or env.vm_ec2_keypair_name
    pem_path = 'roles/%s/%s.pem' % (env.ROLE, name)
    conn = get_ec2_connection()
    kp = conn.get_key_pair(name)
    if kp:
        print('Key pair %s already exists.' % name)
    else:
        # Note, we only get the private key during creation.
        # If we don't save it here, it's lost forever.
        kp = conn.create_key_pair(name)
        open(pem_path, 'wb').write(kp.material)
        os.system('chmod 600 %s' % pem_path)
        print('Key pair %s created.' % name)
    #return kp
    return pem_path

def get_or_create_ec2_instance(name=None, group=None, release=None):
    """
    Creates a new EC2 instance.
    
    You should normally run get_or_create() instead of directly calling this.
    """
    from burlap.common import shelf, OrderedDict
    from boto.exception import EC2ResponseError

    assert name, "A name must be specified."

    conn = get_ec2_connection()

    get_or_create_ec2_security_groups()
    
    pem_path = get_or_create_ec2_key_pair()

    print('Creating EC2 instance from %s...' % (env.vm_ec2_ami,))
    print env.vm_ec2_zone
    reservation = conn.run_instances(
        env.vm_ec2_ami,
        key_name=env.vm_ec2_keypair_name,
        security_groups=env.vm_ec2_selected_security_groups,
        placement=env.vm_ec2_zone,
        instance_type=env.vm_ec2_instance_type)
    instance = reservation.instances[0]
    
    # Name new instance.
    # Note, creation is not instantious, so we may have to wait for a moment
    # before we can access it.
    while 1:
        try:
            if name:
                instance.add_tag(env.vm_name_tag, name)
            if group:
                instance.add_tag(env.vm_group_tag, group)
            if release:
                instance.add_tag(env.vm_release_tag, release)
            break
        except EC2ResponseError as e:
            #print('Unable to set tag: %s' % e)
            print('Waiting for the instance to be created...')
            time.sleep(3)

    # Assign IP.
    if env.vm_ec2_use_elastic_ip:
        # Initialize name/ip mapping since we can't tag elastic IPs.
        shelf.setdefault('vm_elastic_ip_mappings', OrderedDict())
        vm_elastic_ip_mappings = shelf.get('vm_elastic_ip_mappings')
        elastic_ip = vm_elastic_ip_mappings.get(name)
        if not elastic_ip:
            print('Allocating new elastic IP address...')
            addr = conn.allocate_address()
            elastic_ip = addr.public_ip
            print('Allocated address %s.' % elastic_ip)
            vm_elastic_ip_mappings[name] = str(elastic_ip)
            shelf.set('vm_elastic_ip_mappings', vm_elastic_ip_mappings)
            #conn.get_all_addresses()
        while 1:
            try:
                conn.associate_address(
                    instance_id=instance.id,
                    public_ip=elastic_ip)
                print('IP address associated!')
                break
            except EC2ResponseError as e:
                #print('Unable to assign IP: %s' % e)
                print('Waiting for the instance to initialize...')
                time.sleep(3)

#    volume = None
#    if env.vm_ec2_ebs:
#        print 'Creating EBS volume from %s...' % (env.vm_ec2_ebs,)
#        volume = get_ec2_connection().create_volume(10, env.vm_ec2_zone, env.vm_ec2_ebs)
#        print 'Created EBS volume %s.' % (volume.id,)
#    if volume:
#        print 'Attaching EBS volume...',
#        while instance.state == 'pending':
#            sys.stdout.write('.')
#            sys.stdout.flush()
#            time.sleep(1)
#            instance.update()
#        get_ec2_connection().attach_volume(volume.id, instance.id, env.vm_ec2_volume)
#        print 'EBS volume attached.'

    delay = 10
    print 'Stalling for %is for sshd to start...' % delay
    time.sleep(delay)
    
    # Refresh instance reference.
    instance = get_all_ec2_instances(instance_ids=[instance.id])[0]
    assert instance.public_dns_name, 'No public DNS name found!'

    print ""
    print "Login with: ssh -i %s %s@%s" \
        % (pem_path, env.user, instance.public_dns_name)
    print "OR"
    print "fab %(ROLE)s:hostname=%(name)s shell" % dict(name=name, ROLE=env.ROLE)
    
    ip = socket.gethostbyname(instance.public_dns_name)
    print ""
    print """Example hosts entry:
%(ip)s    www.mydomain.com # %(name)s""" % dict(ip=ip, name=name)
    return instance

@task
def exists(name=None, group=None, release=None, except_release=None, verbose=1):
    """
    Determines if a virtual machine instance exists.
    """
    verbose = int(verbose)
    instances = list_instances(
        name=name,
        group=group,
        release=release,
        except_release=except_release,
        show=verbose)
    ret = bool(instances)
    if verbose:
        print('\ninstance %s exist' % ('DOES' if ret else 'does NOT'))
    #return ret
    return instances

@task
def get_or_create(name=None, group=None, config=None, extra=0):
    """
    Creates a virtual machine instance.
    """
    require('vm_type', 'vm_group')
    
    extra = int(extra)
    
    if config:
        config_fn = common.find_template(config)
        config = yaml.load(open(config_fn))
        env.update(config)
        
    env.vm_type = (env.vm_type or '').lower()
    assert env.vm_type, 'No VM type specified.'
    
    group = group or env.vm_group
    assert group, 'No VM group specified.'
    
    ret = exists(name=name, group=group)
    if not extra and ret:
        return ret
    
    today = datetime.date.today()
    release = int('%i%02i%02i' % (today.year, today.month, today.day))
    
    if not name:
        existing_instances = list_instances(group=group, release=release)
        name = env.vm_name_template.format(index=len(existing_instances)+1)
    
    if env.vm_type == EC2:
        return get_or_create_ec2_instance(
            name=name, group=group, release=release)
    else:
        raise NotImplementedError

@task
def delete(name=None, group=None, release=None, except_release=None,
    dryrun=1, verbose=1):
    """
    Permanently erase one or more VM instances from existence.
    """
    dryrun = int(dryrun)
    verbose = int(verbose)
    
    if env.vm_type == EC2:
        conn = get_ec2_connection()
        
        instances = list_instances(
            name=name,
            group=group,
            release=release,
            except_release=except_release,
        )
        
        #print instances
        for instance_name, instance_data in instances.items():
            print('\nDeleting %s (%s)...' \
                % (instance_name, instance_data['id']))
            if not dryrun:
                conn.terminate_instances(instance_ids=[instance_data['id']])
                
    else:
        raise NotImplementedError

@task
def respawn(name, group=None):
    """
    Deletes and recreates one or more VM instances.
    """
    delete(name=name, group=group, dryrun=0)
    get_or_create(name=name, group=group)

@task
def shutdown(force=False):
    #virsh shutdown <name>
    #virsh destroy <name> #to force
    todo

@task
def reboot():
    #virsh reboot <name>
    todo
