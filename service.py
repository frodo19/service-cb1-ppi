import math, os, re, subprocess, xbmc, xbmcaddon, xbmcgui, xbmcvfs
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

# Colours of the per-core values published for skins (AARRGGBB, Kodi [COLOR] tags).
CPU_VALUE_COLOUR = 'FFFFFFFF'   # busy cores
CPU_ZERO_COLOUR = 'FF808080'    # idle cores (00)
CPU_SEP_COLOUR = '80FFFFFF'     # separator of the compact line (white, 50 % opaque)
_CORE = re.compile(r'#(\d+):\s*([^%\s]+)%')
_last = {}


def core_loads(raw):
    """Per-core load from System.CpuUsage; a nan core keeps its last value."""
    out = []
    for core, val in _CORE.findall(raw or ''):
        try:
            v = float(val)
        except ValueError:
            continue
        i = int(core)
        if math.isfinite(v):
            v = max(0.0, min(v, 100.0))
            _last[i] = v
        elif i in _last:
            v = _last[i]
        else:
            continue
        out.append(v)
    return out


def publish_cpu(home):
    """Window(Home) properties for skins: cb1.cores = '| 18 | 24 | 02 |', cb1.coresc = '18|24|02' (compact), cb1.cpu = '14%'."""
    loads = core_loads(xbmc.getInfoLabel('System.CpuUsage'))
    if not loads:
        home.clearProperty('cb1.cores')
        home.clearProperty('cb1.cpu')
        home.clearProperty('cb1.coresc')
        return
    two = []
    for v in loads:
        t = '%02d' % min(int(v), 99)
        col = CPU_ZERO_COLOUR if t == '00' else CPU_VALUE_COLOUR
        two.append('[COLOR %s]%s[/COLOR]' % (col, t))
    home.setProperty('cb1.cores', '| ' + ' | '.join(two) + ' |')
    home.setProperty('cb1.coresc', ('[COLOR %s]|[/COLOR]' % CPU_SEP_COLOUR).join(two))
    home.setProperty('cb1.cpu', '%d%%' % round(sum(loads) / len(loads)))


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
    mon = Mon()
    home = xbmcgui.Window(10000)
    while not mon.waitForAbort(1.0):
        try:
            publish_cpu(home)
        except Exception as e:
            log('cpu property error: %s' % e, xbmc.LOGWARNING)
    for k in ('cb1.cores', 'cb1.coresc', 'cb1.cpu'):
        home.clearProperty(k)
    WEB.stop()
    for dst in reversed(bound):
        unbind(dst)


main()
