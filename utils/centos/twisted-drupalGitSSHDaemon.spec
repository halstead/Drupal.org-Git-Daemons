%{!?python_sitelib: %define python_sitelib %(%{__python}26 -c "from distutils.sysconfig import get_python_lib; print get_python_lib(1)")}

Summary:    A TCP server for drupalGitSSHDaemon
Name:       twisted-drupalGitSSHDaemon
Version:    0.1.8
Release:    1
License:    GPLv2
Group:      Networking/Daemons
Source:     twisted-drupalGitSSHDaemon-%{version}.tar.bz2
BuildRoot:  %{_tmppath}/%{name}-%{version}-root
BuildArch:  noarch
Requires:   python26-twisted, pycrypto26
Requires(post): /sbin/chkconfig, openssh
Requires(preun): /sbin/chkconfig, /sbin/service

%description
Git SSH daemon using Python Twisted

%prep
%setup -q

%build

%install
[ ! -z "$RPM_BUILD_ROOT" -a "$RPM_BUILD_ROOT" != '/' ] 		&& rm -rf "$RPM_BUILD_ROOT"
mkdir -p "$RPM_BUILD_ROOT"/etc/twisted-taps
mkdir -p "$RPM_BUILD_ROOT"%{_initrddir}
mkdir -p "$RPM_BUILD_ROOT"%{_libdir}/twisted-taps
mkdir -p "$RPM_BUILD_ROOT"/etc/twisted-keys
cp "drupaldaemons.cnf.default" "$RPM_BUILD_ROOT"/etc/drupaldaemons.cnf
cp -r "rundir" "$RPM_BUILD_ROOT"/etc/twisted-taps/twisted-drupalGitSSHDaemon
cp -r "drupalpass" "$RPM_BUILD_ROOT"/etc/twisted-taps/twisted-drupalGitSSHDaemon
cp "git-error" "$RPM_BUILD_ROOT"/etc/twisted-taps/twisted-drupalGitSSHDaemon/
cp "drupalGitSSHDaemon.tac" "$RPM_BUILD_ROOT"/etc/twisted-taps/
cp "twisted-drupalGitSSHDaemon.init" "$RPM_BUILD_ROOT"%{_initrddir}/"twisted-drupalGitSSHDaemon"

%clean
[ ! -z "$RPM_BUILD_ROOT" -a "$RPM_BUILD_ROOT" != '/' ] 		&& rm -rf "$RPM_BUILD_ROOT"

%post
if [ $1 -eq 1 ]; then
  /usr/bin/ssh-keygen -t rsa -f /etc/twisted-keys/default -P "" >/dev/null 2>&1 || :
  /sbin/chkconfig --add twisted-drupalGitSSHDaemon
fi

%preun
if [ $1 -eq 0 ]; then
  /sbin/service twisted-drupalGitSSHDaemon stop >/dev/null 2>&1 || :
  /sbin/chkconfig --del twisted-drupalGitSSHDaemon
fi

%files
%defattr(-,root,root,-)
%{_initrddir}/twisted-drupalGitSSHDaemon
%dir %{_libdir}/twisted-taps
/etc/twisted-taps/drupalGitSSHDaemon.tac
%config(noreplace) /etc/drupaldaemons.cnf
/etc/twisted-taps/twisted-drupalGitSSHDaemon/*
/etc/twisted-keys

%changelog
* Fri Sep 14 2012 Jeff Sheltren <jeff@tag1consulting.com>
- Various spec changes/improvements: use macros, add requires

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
