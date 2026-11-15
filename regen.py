import xbmc, xbmcgui, xbmcaddon
import lib

lib.ADDON = xbmcaddon.Addon('service.cb1.ppi')
lib.generate()
xbmc.executebuiltin('ReloadSkin()')
xbmcgui.Dialog().notification('CB1 PPI', 'Panel regenerated' if lib.lang() == 'en' else 'A panel újragenerálva', xbmcgui.NOTIFICATION_INFO, 3000)
