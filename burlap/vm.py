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
except ImportError:
    boto = None

EC2 = 'ec2'

env.NAME_TAG = 'Name'
env.GROUP_TAG = 'Group'

env.vm_type = None

env.vm_ec2_account_id = None
# https://help.ubuntu.com/community/EC2StartersGuide#Official_Ubuntu_Cloud_Guest_Amazon_Machine_Images_.28AMIs.29
env.vm_ec2_ami = None # e.g. 'ami-a29943cb'
env.vm_ec2_instance_type = None # e.g. 'm1.small'
env.vm_ec2_ebs = None
env.vm_ec2_zone = None # e.g. 'us-east-1d'
env.vm_ec2_available_security_groups = {} # {(name,desc):[(protocol, port, port, ip_range)]
env.vm_ec2_selected_security_groups = []
env.vm_ec2_aws_key = None
env.vm_ec2_volume = '/dev/sdh1'

def retrieve_ec2_hosts():
    for name, data in list(show=0).iteritems():
        yield data.dns_name

env.hosts_retrievers['ec2'] = retrieve_ec2_hosts

def translate_ec2_hostname(hostname):
    for name, data in list(show=0).iteritems():
        if name == hostname:
            return data.dns_name

env.hostname_translators['ec2'] = translate_ec2_hostname

def _ec2():
    assert 'AWS_CREDENTIAL_FILE' in os.environ, \
        'AWS environment variables not set.'
    return boto.connect_ec2()

def _ec2_fetch_instances():
    return sum(map(lambda r: r.instances, _ec2().get_all_instances()), [])

def _ec2_fetch_running_instances():
    instances = filter(lambda i: i.state == 'running', _ec2_fetch_instances())
    instances.reverse()
    return instances

@task
def list(show=1):
    """
    Retrieves all virtual machines instances in the current environment.
    """
    require('vm_type', 'vm_group')
    #print 'env.vm_typeL:',env.vm_type
    assert env.vm_type, 'No VM type specified.'
    #assert env.vm_group, 'No VM group specified.'
    env.vm_type = (env.vm_type or '').lower()
    data = type(env)()
    if env.vm_type == EC2:
        for instance in _ec2_fetch_running_instances():
            name = instance.tags.get(env.NAME_TAG)
            group = instance.tags.get(env.GROUP_TAG)
#            print 'name:',name
#            print 'group:',group,env.vm_group
            if env.vm_group and env.vm_group != group:
                continue
            data.setdefault(name, type(env)())
            data[name]['id'] = instance.id
            data[name]['dns_name'] = instance.dns_name
            data[name]['ip'] = socket.gethostbyname(instance.dns_name)
        if int(show):
            pprint.pprint(data, indent=4)
        return data
    elif env.vm_type == KVM:
        #virsh list
        pass
    else:
        raise NotImplementedError

def _create_ec2_security_group(group):
    """Creates a security group opening 22, 80 and 443"""
    try:
        for authorizations in env.vm_ec2_available_security_groups[group]:
            app = _ec2().create_security_group(
                group,
                group,#security_group_desc,
            )
            for protocol, inport, outport, ip_range in authorizations:
                print 'Authorizing:',protocol, inport, outport, ip_range
                if ip_range:
                    app.authorize(protocol, inport, outport, ip_range)
                else:
                    app.authorize(protocol, inport, outport, None, app)
            print "Created security group %s." % (security_group_name,)
            
    except boto.exception.EC2ResponseError:
        print "Security group called %s already exists, continuing." % group
        return False
    return True

def _create_ec2_instance(name, group):
    """Makes a new app instance with an EBS volume"""

    print 'Creating EC2 security groups...'
    for security_group in env.vm_ec2_selected_security_groups:
        _create_ec2_security_group(security_group)
    
    volume = None
    if env.vm_ec2_ebs:
        print 'Creating EBS volume from %s...' % (env.vm_ec2_ebs,)
        volume = _ec2().create_volume(10, env.vm_ec2_zone, env.vm_ec2_ebs)
        print 'Created EBS volume %s.' % (volume.id,)

    print 'Starting EC2 instance from %s...' % (env.vm_ec2_ami,)
    reservation = _ec2().run_instances(
        env.vm_ec2_ami,
        key_name=env.vm_ec2_aws_key,
        security_groups=env.vm_ec2_selected_security_groups,
        placement=env.vm_ec2_zone,
        instance_type=env.vm_ec2_instance_type)
    instance = reservation.instances[0]
    print 'Started EC2 instance %s from %s...' \
        % (instance.id, env.vm_ec2_ami)
        
    # Name new instance.
    instance.add_tag(env.NAME_TAG, name)
    instance.add_tag(env.GROUP_TAG, group)

    if volume:
        print 'Attaching EBS volume...',
        while instance.state == 'pending':
            sys.stdout.write('.')
            sys.stdout.flush()
            time.sleep(1)
            instance.update()
        _ec2().attach_volume(volume.id, instance.id, env.vm_ec2_volume)
        print 'EBS volume attached.'

    print 'Stalling for 30s for sshd to start...'
    time.sleep(30)

    print ""
    print "Login with: ssh -i %s.pem %s@%s" \
        % (env.vm_ec2_aws_key, env.user, instance.dns_name)
    print "OR"
    print "fab %(ROLE)s:hostname=%(name)s shell" % dict(name=name, ROLE=env.ROLE)
    
    ip = socket.gethostbyname(instance.dns_name)
    print ""
    print """Example hosts entry:
%(ip)s    www.mydomain.com # %(name)s""" % dict(ip=ip, name=name)
    return instance

@task
def create(name, config):
    require('vm_type', 'vm_group')
    config_fn = common.find_template(config)
    config = yaml.load(open(config_fn))
    env.update(config)
    env.vm_type = (env.vm_type or '').lower()
    assert env.vm_type, 'No VM type specified.'
    assert env.vm_group, 'No VM group specified.'
    if env.vm_type == EC2:
        _create_ec2_instance(name=name, group=env.vm_group)
    else:
        raise NotImplementedError

@task
def shutdown(force=False):
    #virsh shutdown <name>
    #virsh destroy <name> #to force
    todo

@task
def reboot():
    #virsh reboot <name>
    todo
    