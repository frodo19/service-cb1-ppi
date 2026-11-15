import os, subprocess, xbmc, xbmcaddon, xbmcgui, xbmcvfs
import lib, web, media

ADDON = xbmcaddon.Addon()
SRC = os.path.join(lib.ROOT, 'media')
DST = '/usr/share/kodi/media'
log = lib.log


def mounted(path):
    try:
        with open('/proc/mounts') as f:
            return any(l.split()[1] == path for l in f)
    except OSError:
        return False


def bind(src, dst):
    while mounted(dst):
        subprocess.call(['umount', '-l', dst])
    r = subprocess.run(['mount', '--bind', src, dst], capture_output=True, text=True)
    if r.returncode:
        log('bind failed %s -> %s: %s' % (src, dst, r.stderr.strip()), xbmc.LOGERROR)
        return False
    log('bind ok: %s -> %s' % (src, dst))
    return True


def unbind(dst):
    while mounted(dst):
        if subprocess.call(['umount', '-l', dst]):
            break
    log('unmounted: ' + dst)


WEB = web.Web()


class Mon(xbmc.Monitor):
    def onNotification(self, sender, method, data):
        if method.startswith('VideoLibrary.On'):
            media.bump()

    def onSettingsChanged(self):
        lib.ADDON = xbmcaddon.Addon('service.cb1.ppi')  # fresh settings
        WEB.apply()
        lib.generate()
        if lib.ADDON.getSetting('reload_after') != 'false':
            xbmc.executebuiltin('ReloadSkin()')


class Ply(xbmc.Player):
    """The fork refreshes the DV.* window properties only while the panel is open,
    so at playback start the panel is opened and closed invisibly."""
    def onAVStarted(self):
        try:
            if xbmcaddon.Addon('service.cb1.ppi').getSetting('refresh_on_start') == 'false':
                return
            if not self.isPlayingVideo():
                return
            home = xbmcgui.Window(10000)
            home.setProperty('cb1.silent', '1')
            xbmc.executebuiltin('ActivateWindow(playerprocessinfo)')
            xbmc.sleep(1200)
            xbmc.executebuiltin('Dialog.Close(playerprocessinfo,true)')
            xbmc.sleep(300)
            home.clearProperty('cb1.silent')
            log('DV data refreshed (silent panel open)')
        except Exception as e:
            log('silent refresh error: %s' % e, xbmc.LOGWARNING)
            xbmcgui.Window(10000).clearProperty('cb1.silent')


def main():
    lib.generate()
    bound = []
    if os.path.isdir(DST):
        for name in sorted(os.listdir(SRC)):
            dst = os.path.join(DST, name)
            if not os.path.exists(dst):
                log('not present on this system, skipped: ' + name, xbmc.LOGWARNING)
                continue
            if bind(os.path.join(SRC, name), dst):
                bound.append(dst)
    else:
        log('%s missing, skipped' % DST, xbmc.LOGWARNING)
    ply = Ply()  # noqa: F841 (must be kept alive)
    WEB.apply()
    Mon().waitForAbort()
    WEB.stop()
    for dst in reversed(bound):
        unbind(dst)


main()
