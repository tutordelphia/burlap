from __future__ import print_function

import os
import sys
import tempfile

from burlap import Satchel
from burlap.constants import *
from burlap.decorators import task

class PackagerSatchel(Satchel):
    
    name = 'packager'
    
    def set_defaults(self):
        self.env.apt_requirments_fn = 'apt-requirements.txt'
        self.env.yum_requirments_fn = 'yum-requirements.txt'
        self.env.initial_upgrade = True
        self.env.apt_packages = None
        self.env.yum_packages = None
        self.env.do_reboots = True
    
    def record_manifest(self):
        """
        Returns a dictionary representing a serialized state of the service.
        """
        data = {}
        data['required_packages'] = self.install_required(type=SYSTEM, verbose=False, list_only=True)
        data['required_packages'].sort()
        data['custom_packages'] = self.install_custom(list_only=True)
        data['custom_packages'].sort()
        data['repositories'] = self.get_repositories()
        return data
    
    @task
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
            raise Exception('Unknown packager: %s' % (packager,))

    @task
    def install_apt(self, fn=None, package_name=None, update=0, list_only=0):
        """
        Installs system packages listed in apt-requirements.txt.
        """
        r = self.local_renderer
        assert self.genv[ROLE]
        apt_req_fqfn = fn or self.find_template(self.env.apt_requirments_fn)
        if not apt_req_fqfn:
            return []
        assert os.path.isfile(apt_req_fqfn)
        
        lines = list(self.env.apt_packages or [])
        for _ in open(apt_req_fqfn).readlines():
            if _.strip() and not _.strip().startswith('#') \
            and (not package_name or _.strip() == package_name):
                lines.extend(_pkg.strip() for _pkg in _.split(' ') if _pkg.strip()) 
        
        if list_only:
            return lines
        
        tmp_fn = r.write_temp_file('\n'.join(lines))
        apt_req_fqfn = tmp_fn
        
        if not self.genv.is_local:
            r.put(local_path=tmp_fn)
            apt_req_fqfn = self.genv.put_remote_path
        r.sudo('apt-get update -y --fix-missing')
        r.sudo('apt-get install -y `cat "%s" | tr "\\n" " "`' % apt_req_fqfn)

    @task
    def install_yum(self, fn=None, package_name=None, update=0, list_only=0):
        """
        Installs system packages listed in yum-requirements.txt.
        """
        assert self.genv[ROLE]
        yum_req_fn = fn or self.find_template(self.genv.yum_requirments_fn)
        if not yum_req_fn:
            return []
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

    @task
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
            raise Exception('Unknown packager: %s' % (packager,))
    
    @task
    def kill_apt_get(self):
        r = self.local_renderer
        r.sudo('killall apt-get')
        r.sudo('dpkg --configure -a')
    
    @task
    def refresh(self, *args, **kwargs):
        """
        Updates/upgrades all system packages.
        """
        r = self.local_renderer
        packager = self.packager
        if packager == APT:
            r.sudo('apt-get update -y --fix-missing')
        elif package == YUM:
            raise NotImplementedError
            #return upgrade_yum(*args, **kwargs)
        else:
            raise Exception('Unknown packager: %s' % (packager,))

    @task
    def upgrade(self):
        """
        Updates/upgrades all system packages.
        """
        r = self.local_renderer
        packager = self.packager
        if packager == APT:
            r.sudo('apt-get upgrade -y')
            r.sudo('apt-get dist-upgrade -y')
        elif package == YUM:
            raise NotImplementedError
        else:
            raise Exception('Unknown packager: %s' % (packager,))

    @task
    def get_repositories(self, typ=None, service=None):
        
        service = (service or '').strip().upper()
        typ = (typ or '').lower().strip()
        assert not typ or typ in PACKAGE_TYPES, \
            'Unknown package type: %s' % (typ,)
        
        repositories = {} # {typ: [repos]}
        
        for satchel_name, satchel in self.all_other_enabled_satchels.items():
            
            if service and satchel_name != service:
                continue
            
            if hasattr(satchel, 'packager_repositories'):
                repos = satchel.packager_repositories
                for repo_type, repo_lst in repos.items():
                    assert isinstance(repo_lst, (tuple, list)), \
                        'Invalid repo list for satchel %s.' % satchel_name
                    for _name in repo_lst:
                        # Can be string (for APT) or tuple of strings (for APT SOURCE)
                        if isinstance(_name, basestring):
                            _name = _name.strip()
                            assert _name, 'Invalid repo name for satchel %s.' % satchel_name
                    repositories.setdefault(repo_type, [])
                    repositories[repo_type].extend(repo_lst)
                    
        for repo_type in repositories:
            repositories[repo_type].sort()
                    
        return repositories
    
    @task
    def install_repositories(self, *args, **kwargs):
        r = self.local_renderer
        repos = self.get_repositories(*args, **kwargs)
        
        # Apt sources.
        r.pc('Installing apt sources.')
        apt_sources = repos.get(APT_SOURCE, [])
        for line, fn in apt_sources:
            r.env.apt_source = line
            r.env.apt_fn = fn
            r.sudo("sh -c 'echo \"{apt_source}\" > {apt_fn}'")
        
        # Apt keys.
        r.pc('Installing apt keys.')
        apt_keys = repos.get(APT_KEY, [])
        for parts in apt_keys:
            if isinstance(parts, tuple):
                r.env.apt_key_server = key_server
                r.env.apt_key_value = key_value
                r.sudo("apt-key adv --keyserver {apt_key_server} --recv-key {apt_key_value}")
            else:
                assert isinstance(parts, basestring)
                r.env.apt_key_url = parts
                r.sudo('wget {apt_key_url} -O - | apt-key add -')
        
        r.pc('Installing repositories.')
        for repo_type in [APT]:
            if repo_type not in repos:
                continue
            repo_lst = repos[repo_type]
            if repo_type is APT:
                for repo_name in repo_lst:
                    r.env.repo_name = repo_name
                    r.sudo('add-apt-repository -y {repo_name}')
                r.sudo('apt-get update -y')
            else:
                raise NotImplementedError, 'Unsupported repository type: %s' % repo_type

    @task
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
        
        for _service, satchel in self.all_other_enabled_satchels.items():
                
            _service = _service.strip().upper()
            if service and service != _service:
                continue
                
            _new = []
            
            if not type or type == SYSTEM:
                
                #TODO:deprecated, remove
                _new.extend(required_system_packages.get(
                    _service, {}).get((version.distro, version.release), []))
                    
                try:
                    _pkgs = satchel.packager_system_packages
                    for _key in [(version.distro, version.release), version.distro]:
                        if _key in _pkgs:
                            _new.extend(_pkgs[_key])
                except AttributeError:
                    pass
                    
            if not type or type == PYTHON:
                
                #TODO:deprecated, remove
                _new.extend(required_python_packages.get(
                    _service, {}).get((version.distro, version.release), []))
                
                try:
                    _pkgs = satchel.packager_python_packages
                    for _key in [(version.distro, version.release), version.distro]:
                        if _key in _pkgs:
                            _new.extend(_pkgs[_key])
                except AttributeError:
                    pass
                print('_new:', _new)
                    
            if not type or type == RUBY:
                
                #TODO:deprecated, remove
                _new.extend(required_ruby_packages.get(
                    _service, {}).get((version.distro, version.release), []))
            
            
            
    #         if not _new and verbose:
    #             print(\
    #                 'Warning: no packages found for service "%s"' % (_service,)
            for _ in _new:
                if _ in packages_set:
                    continue
                packages_set.add(_)
                packages.append(_)
        if self.verbose:
            for package in sorted(packages):
                print('package:', package)
        return packages
    
    def get_locale(self):
        version = self.os_version
        all_locale_dicts = {}
        for satchel_name, satchel in self.all_other_enabled_satchels.items():
#             print('satchel_name:',satchel_name)
            try:
                locale_dict = satchel.packager_locale.get(version.distro, {})
#                 print('locale_dict:',locale_dict)
                for _k, _v in locale_dict.items():
                    assert all_locale_dicts.get(_k, _v) == _v
                    all_locale_dicts[_k] = _v
            except AttributeError:
                pass
        return all_locale_dicts
    
    @task
    def update_locale(self):
        locale_dict = self.get_locale()
        r = self.local_renderer
        packager = self.packager
        if packager == APT:
            r.env.locale_string = ' '.join('%s=%s' % (_k, _v) for _k, _v in locale_dict.items())
            r.sudo('update-locale {locale_string}')
        elif package == YUM:
            raise NotImplementedError
        else:
            raise Exception('Unknown packager: %s' % (packager,))
    
    @task
    def install_required(self, type=None, service=None, list_only=0, **kwargs):
        """
        Installs system packages listed as required by services this host uses.
        """
        r = self.local_renderer
        r.pc('Installing required packages.')
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
                    if self.verbose:
                        print('content:', content)
                    break
                fd, fn = tempfile.mkstemp()
                fout = open(fn, 'w')
                fout.write(content)
                fout.close()
                self.install_custom(fn=fn)
            else:
                raise NotImplementedError
        return lst

    @task
    def configure(self, **kwargs):
        
        lm = self.last_manifest
        
        if isinstance(lm, list):
            lm = {'required_packages': lm}
        #lm_passwords = lm.get('passwords', {})
        
        enabled_services = map(str.upper, self.genv.services)
        #for satchel_name, satchel in self.all_satchels.iteritems():
        for satchel_name, satchel in self.all_other_enabled_satchels.items():
            if hasattr(satchel, 'packager_pre_configure'):
                satchel.packager_pre_configure()
                
        self.refresh()
        
        if lm.get('initial_upgrade') is None and self.env.initial_upgrade:
            self.upgrade()
            if self.env.do_reboots:
                self.reboot(wait=300, timeout=60)
            
        self.install_repositories(**kwargs)
        self.install_required(type=SYSTEM, **kwargs)
        self.install_custom(**kwargs)
    
    configure.deploy_before = ['user', 'ubuntumultiverse']

class UbuntuMultiverseSatchel(Satchel):
     
    name = 'ubuntumultiverse'
    
    @task
    def configure(self):
        """
        Returns one or more Deployer instances, representing tasks to run during a deployment.
        """
        r = self.local_renderer
        if self.env.enabled:
            # Enable the multiverse so we can install select non-free packages.
            r.sudo('sed -i "/^# deb.*multiverse/ s/^# //" /etc/apt/sources.list')
            r.sudo('apt-get update')
        else:
            # Disable the multiverse.
            r.sudo('sed -i "/^# // s/^# deb.*multiverse/" /etc/apt/sources.list')
            r.sudo('apt-get update')
    
    configure.deploy_before = []

packager = PackagerSatchel()
umv = UbuntuMultiverseSatchel()
