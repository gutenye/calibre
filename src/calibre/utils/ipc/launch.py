#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import with_statement

__license__   = 'GPL v3'
__copyright__ = '2009, Kovid Goyal <kovid@kovidgoyal.net>'
__docformat__ = 'restructuredtext en'

import subprocess, os, sys, time

from calibre.constants import iswindows, isosx, isfrozen
from calibre.utils.config import prefs
from calibre.ptempfile import PersistentTemporaryFile

if iswindows:
    import win32process

class Worker(object):
    '''
    Platform independent object for launching child processes. All processes
    have the environment variable :envvar:`CALIBRE_WORKER` set.

    Useful attributes: ``is_alive``, ``returncode``
    usefule methods: ``kill``

    To launch child simply call the Worker object. By default, the child's
    output is redirected to an on disk file, the path to which is returned by
    the call.
    '''

    @property
    def osx_interpreter(self):
        exe = os.path.basename(sys.executable)
        return exe if 'python' in exe else 'python'

    @property
    def osx_contents_dir(self):
        fd = os.path.realpath(getattr(sys, 'frameworks_dir'))
        return os.path.dirname(fd)

    @property
    def executable(self):
        if iswindows:
            return os.path.join(os.path.dirname(sys.executable),
                   'calibre-parallel.exe' if isfrozen else \
                           'Scripts\\calibre-parallel.exe')
        if isosx:
            if not isfrozen: return 'calibre-parallel'
            contents = os.path.join(self.osx_contents_dir,
                    'console.app', 'Contents')
            return os.path.join(contents, 'MacOS', self.osx_interpreter)

        return os.path.join(getattr(sys, 'frozen_path'), 'calibre-parallel') \
                            if isfrozen else 'calibre-parallel'

    @property
    def gui_executable(self):
        if isfrozen and isosx:
            return os.path.join(self.osx_contents_dir,
                    'MacOS', self.osx_interpreter)

        return self.executable

    @property
    def env(self):
        env = dict(os.environ)
        env['CALIBRE_WORKER'] = '1'
        env.update(self._env)
        return env

    @property
    def is_alive(self):
        return hasattr(self, 'child') and self.child.poll() is not None

    @property
    def returncode(self):
        if not hasattr(self, 'child'): return None
        self.child.poll()
        return self.child.returncode

    def kill(self):
        try:
            if self.is_alive:
                if iswindows:
                    return self.child.kill()
                try:
                    self.child.terminate()
                    st = time.time()
                    while self.is_alive and time.time()-st < 2:
                        time.sleep(0.2)
                finally:
                    if self.is_alive:
                        self.child.kill()
        except:
            pass

    def __init__(self, env, gui=False):
        self._env = {}
        self.gui = gui
        if isosx and isfrozen:
            contents = os.path.join(self.osx_contents_dir, 'console.app', 'Contents')
            resources = os.path.join(contents, 'Resources')
            fd = os.path.join(contents, 'Frameworks')
            self._env['PYTHONHOME']  = resources
            self._env['MAGICK_HOME'] = os.path.join(fd, 'ImageMagick')
            self._env['DYLD_LIBRARY_PATH'] = os.path.join(fd, 'ImageMagick', 'lib')
        if isfrozen and not (iswindows or isosx):
            self._env['LD_LIBRARY_PATH'] = getattr(sys, 'frozen_path') + ':'\
                    + os.environ.get('LD_LIBRARY_PATH', '')
        self._env.update(env)

    def __call__(self, redirect_output=True, cwd=None, priority=None):
        '''
        If redirect_output is True, output from the child is redirected
        to a file on disk and this method returns the path to that file.
        '''
        exe = self.gui_executable if self.gui else self.executable
        env = self.env
        env['ORIGWD'] = cwd or os.path.abspath(os.getcwd())
        _cwd = cwd
        if isfrozen and not iswindows and not isosx:
            _cwd = getattr(sys, 'frozen_path', None)
        if priority is None:
            priority = prefs['worker_process_priority']
        cmd = [exe]
        if isosx:
            cmd += ['-c', 'from calibre.utils.worker import main; main()']
        args = {
                'env' : env,
                'cwd' : _cwd,
                }
        if iswindows:
            priority = {
                    'high'   : win32process.HIGH_PRIORITY_CLASS,
                    'normal' : win32process.NORMAL_PRIORITY_CLASS,
                    'low'    : win32process.IDLE_PRIORITY_CLASS}[priority]
            args['creationflags'] = win32process.CREATE_NO_WINDOW|priority
        ret = None
        if redirect_output:
            self._file = PersistentTemporaryFile('_worker_redirect.log')
            args['stdout'] = self._file._fd
            args['stderr'] = subprocess.STDOUT
            ret = self._file.name

        self.child = subprocess.Popen(cmd, **args)

        return ret



