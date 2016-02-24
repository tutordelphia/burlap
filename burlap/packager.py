import os
import sys
import tempfile

from burlap.constants import *
from burlap import Satchel

class PackagerSatchel(Satchel):
    
    name = 'packager'
    
    tasks = (
        'configure',
        'prepare',
        'install_apt',
        'install_custom',
        'refresh',
        'refresh_apt',
        'upgrade',
        'list_required',
        'install_required',
        'kill_apt_get',
    )
    
    def set_defaults(self):
        self.env.apt_requirments_fn = 'apt-requirements.txt'
        self.env.yum_requirments_fn = 'yum-requirements.txt'
    
    def record_manifest(self):
        """
        Returns a dictionary representing a serialized state of the service.
        """
        data = []
        
        data.extend(self.install_required(type=SYSTEM, verbose=False, list_only=True))
        data.extend(self.install_custom(list_only=True))
        
        data.sort()
        return data
        
    def prepare(self):
        """
        Preparse the packaging system for installations.
        """
        packager = self.packager
        if packager == APT:
            self.sudo_or_dryrun('apt-get update')
        elif package == YUM:
            self.sudo_or_dryrun('yum update')
        else:
            raise Exception, 'Unknown packager: %s' % (packager,)

    def install_apt(self, fn=None, package_name=None, update=0, list_only=0):
        """
        Installs system packages listed in apt-requirements.txt.
        """
        assert self.genv[ROLE]
        apt_req_fqfn = fn or self.find_template(self.env.apt_requirments_fn)
        assert os.path.isfile(apt_req_fqfn)
        lines = [
            _.strip() for _ in open(apt_req_fqfn).readlines()
            if _.strip() and not _.strip().startswith('#')
            and (not package_name or _.strip() == package_name)
        ]
        if list_only:
            return lines
        fd, tmp_fn = tempfile.mkstemp()
        fout = open(tmp_fn, 'w')
        fout.write('\n'.join(lines))
        fout.close()
        apt_req_fqfn = tmp_fn
        if not self.genv.is_local:
            self.put_or_dryrun(local_path=tmp_fn)
            apt_req_fqfn = self.genv.put_remote_path
    #    if int(update):
        self.sudo_or_dryrun('apt-get update -y --fix-missing')
        self.sudo_or_dryrun('apt-get install -y `cat "%s" | tr "\\n" " "`' % apt_req_fqfn)

    def install_yum(self, fn=None, package_name=None, update=0, list_only=0):
        """
        Installs system packages listed in yum-requirements.txt.
        """
        assert self.genv[ROLE]
        yum_req_fn = fn or self.find_template(self.genv.yum_requirments_fn)
        assert os.path.isfile(yum_req_fn)
        update = int(update)
        if list_only:
            return [
                _.strip() for _ in open(yum_req_fn).readlines()
                if _.strip() and not _.strip.startswith('#')
                and (not package_name or _.strip() == package_name)
            ]
        if update:
            self.sudo_or_dryrun('yum update --assumeyes')
        if package_name:
            self.sudo_or_dryrun('yum install --assumeyes %s' % package_name)
        else:
            if self.genv.is_local:
                self.put_or_dryrun(local_path=yum_req_fn)
                yum_req_fn = self.genv.put_remote_fn
            self.sudo_or_dryrun('yum install --assumeyes $(cat %(yum_req_fn)s)' % yum_req_fn)

    def install_custom(self, *args, **kwargs):
        """
        Installs all system packages listed in the appropriate
        <packager>-requirements.txt.
        """
        packager = self.packager
        if packager == APT:
            return self.install_apt(*args, **kwargs)
        elif package == YUM:
            return self.install_yum(*args, **kwargs)
        else:
            raise Exception, 'Unknown packager: %s' % (packager,)
    
    def kill_apt_get(self):
        self.sudo_or_dryrun('killall apt-get')
        self.sudo_or_dryrun('dpkg --configure -a')
    
    def refresh(self, *args, **kwargs):
        """
        Updates/upgrades all system packages.
        """
        packager = self.packager
        if packager == APT:
            return self.refresh_apt(*args, **kwargs)
        elif package == YUM:
            raise NotImplementedError
            #return upgrade_yum(*args, **kwargs)
        else:
            raise Exception, 'Unknown packager: %s' % (packager,)
    
    def refresh_apt(self):
        self.sudo_or_dryrun('apt-get update -y --fix-missing')
    
    def upgrade(self, *args, **kwargs):
        """
        Updates/upgrades all system packages.
        """
        packager = self.packager
        if packager == APT:
            #return self.upgrade_apt(*args, **kwargs)
            return self.sudo_or_dryrun('apt-get upgrade -y')
        elif package == YUM:
            raise NotImplementedError
            #return upgrade_yum(*args, **kwargs)
        else:
            raise Exception, 'Unknown packager: %s' % (packager,)

    def list_required(self, type=None, service=None):
        """
        Displays all packages required by the current role
        based on the documented services provided.
        """
        from burlap.common import (
            required_system_packages,
            required_python_packages,
            required_ruby_packages,
        )
        service = (service or '').strip().upper()
        type = (type or '').lower().strip()
        assert not type or type in PACKAGE_TYPES, \
            'Unknown package type: %s' % (type,)
        packages_set = set()
        packages = []
        version = self.os_version
        for _service in self.genv.services:
            _service = _service.strip().upper()
            if service and service != _service:
                continue
            _new = []
            if not type or type == SYSTEM:
                _new.extend(required_system_packages.get(
                    _service, {}).get((version.distro, version.release), []))
            if not type or type == PYTHON:
                _new.extend(required_python_packages.get(
                    _service, {}).get((version.distro, version.release), []))
            if not type or type == RUBY:
                _new.extend(required_ruby_packages.get(
                    _service, {}).get((version.distro, version.release), []))
    #         if not _new and verbose:
    #             print>>sys.stderr, \
    #                 'Warning: no packages found for service "%s"' % (_service,)
            for _ in _new:
                if _ in packages_set:
                    continue
                packages_set.add(_)
                packages.append(_)
        if self.verbose:
            for package in sorted(packages):
                print 'package:', package
        return packages
    
    def install_required(self, type=None, service=None, list_only=0, verbose=0, **kwargs):
        """
        Installs system packages listed as required by services this host uses.
        """
        verbose = int(verbose)
        list_only = int(list_only)
        type = (type or '').lower().strip()
        assert not type or type in PACKAGE_TYPES, \
            'Unknown package type: %s' % (type,)
        lst = []
        if type:
            types = [type]
        else:
            types = PACKAGE_TYPES
        for type in types:
            if type == SYSTEM:
                content = '\n'.join(self.list_required(type=type, service=service))
                if list_only:
                    lst.extend(_ for _ in content.split('\n') if _.strip())
                    if verbose:
                        print 'content:', content
                    break
                fd, fn = tempfile.mkstemp()
                fout = open(fn, 'w')
                fout.write(content)
                fout.close()
                self.install_custom(fn=fn)
            else:
                raise NotImplementedError
        return lst

    def configure(self, **kwargs):
        for satchel_name, satchel in self.all_satchels.iteritems():
            if hasattr(satchel, 'packager_pre_configure'):
                satchel.packager_pre_configure()
        self.refresh()
        self.install_required(type=SYSTEM, **kwargs)
        self.install_custom(**kwargs)
    configure.is_deployer = True
    configure.deploy_before = ['user', 'ubuntumultiverse']

class UbuntuMultiverseSatchel(Satchel):
     
    name = 'ubuntumultiverse'
     
    tasks = (
        'configure',
    )
         
    def configure(self):
        """
        Returns one or more Deployer instances, representing tasks to run during a deployment.
        """
        if self.env.enabled:
            # Enable the multiverse so we can install select non-free packages.
            self.sudo_or_dryrun('sed -i "/^# deb.*multiverse/ s/^# //" /etc/apt/sources.list')
            self.sudo_or_dryrun('apt-get update')
        else:
            # Disable the multiverse.
            self.sudo_or_dryrun('sed -i "/^# // s/^# deb.*multiverse/" /etc/apt/sources.list')
            self.sudo_or_dryrun('apt-get update')
             
    configure.is_deployer = True
    configure.deploy_before = []

packager = PackagerSatchel()
umv = UbuntuMultiverseSatchel()
