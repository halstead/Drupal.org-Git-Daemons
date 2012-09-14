%{!?python_sitelib: %define python_sitelib %(%{__python}26 -c "from distutils.sysconfig import get_python_lib; print get_python_lib(1)")}

Summary:    A TCP server for drupalGitSSHDaemon
Name:       twisted-drupalGitSSHDaemon
Version:    0.1.7
Release:    1
License:    Unknown
Group:      Networking/Daemons
Source:     twisted-drupalGitSSHDaemon-%{version}.tar.bz2
BuildRoot:  %{_tmppath}/%{name}-%{version}-root
BuildArch:  noarch
Requires:   python26-twisted
Requires(post): /sbin/chkconfig
Requires(preun): /sbin/chkconfig, /sbin/service
Requires(postun): /sbin/service

%description
Patched from the "automatically created by tap2rpm" rpm

%prep
%setup
%build

%install
[ ! -z "$RPM_BUILD_ROOT" -a "$RPM_BUILD_ROOT" != '/' ] 		&& rm -rf "$RPM_BUILD_ROOT"
mkdir -p "$RPM_BUILD_ROOT"/etc/twisted-taps
mkdir -p "$RPM_BUILD_ROOT"/etc/init.d
mkdir -p "$RPM_BUILD_ROOT"/var/lib/twisted-taps
mkdir -p "$RPM_BUILD_ROOT"/etc/twisted-keys
cp "drupaldaemons.cnf.default" "$RPM_BUILD_ROOT"/etc/drupaldaemons.cnf
cp -r "rundir" "$RPM_BUILD_ROOT"/etc/twisted-taps/twisted-drupalGitSSHDaemon
cp "git-error" "$RPM_BUILD_ROOT"/etc/twisted-taps/twisted-drupalGitSSHDaemon/
cp "drupalGitSSHDaemon.tac" "$RPM_BUILD_ROOT"/etc/twisted-taps/
cp "twisted-drupalGitSSHDaemon.init" "$RPM_BUILD_ROOT"/etc/init.d/"twisted-drupalGitSSHDaemon"

%clean
[ ! -z "$RPM_BUILD_ROOT" -a "$RPM_BUILD_ROOT" != '/' ] 		&& rm -rf "$RPM_BUILD_ROOT"

%post
/usr/bin/ssh-keygen -t rsa -f /etc/twisted-keys/default -P ""
/sbin/chkconfig --add twisted-drupalGitSSHDaemon
/sbin/chkconfig --level 35 twisted-drupalGitSSHDaemon
/sbin/service twisted-drupalGitSSHDaemon start

%preun
/sbin/service twisted-drupalGitSSHDaemon stop
/sbin/chkconfig --del twisted-drupalGitSSHDaemon

%files
%defattr(-,root,root)
%attr(0755,root,root) /etc/init.d/twisted-drupalGitSSHDaemon
%attr(0660,root,root) /etc/twisted-taps/drupalGitSSHDaemon.tac
%attr(0660,root,root) /etc/drupaldaemons.cnf
%attr(0660,root,root) /etc/twisted-taps/twisted-drupalGitSSHDaemon/config.py
%attr(0660,root,root) /etc/twisted-taps/twisted-drupalGitSSHDaemon/drupalGitSSHDaemon.py
%attr(0755,root,root) /etc/twisted-taps/twisted-drupalGitSSHDaemon/git-error
%attr(0660,root,root) /etc/twisted-taps/twisted-drupalGitSSHDaemon/service/__init__.py
%attr(0660,root,root) /etc/twisted-taps/twisted-drupalGitSSHDaemon/service/protocols.py
%attr(0660,root,root) /etc/twisted-keys

%changelog
* Thu Aug 16 2012 Michael Halstead <halstead@happypunch.com>
- Added compatiblity with PHPass style hashed passwords
* Sun Feb 20 2011 Trevor Hardcastle <chizu@spicious.com>
- Bug fixes around error handling
- Respect push control settings
* Sat Feb 19 2011 Trevor Hardcastle <chizu@spicious.com>
- Updated error messages (Sam Boyer)
- Reroll for missed commit
* Fri Feb 18 2011 Trevor Hardcastle <chizu@spicious.com>
- Leading slash in project URLs is optional
- Use epoll instead of select
* Thu Feb 10 2011 Trevor Hardcastle <chizu@spicious.com>
- Force git-error to use Python 2.6
- Allow more flexible http configuration
* Tue Feb 08 2011 Trevor Hardcastle <chizu@spicious.com>
- Fixes global flags
- Include the auth data in the git-shell environment
- Resolve packaging problems related to the use of python submodules
* Sun Jan 09 2011 Trevor Hardcastle <chizu@spicious.com>
- Created by tap2rpm: twisted-drupalGitSSHDaemon (0.1)
