import os, re, xbmc, xbmcaddon, xbmcvfs

import strings_en

ADDON = xbmcaddon.Addon('service.cb1.ppi')
ROOT = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
TPL = os.path.join(ROOT, 'template', 'cb1')
OUT = os.path.join(ROOT, 'media', 'cb1')

# role -> (default RRGGBB, colours used in the original XML)
TEXT_ROLES = {
    't_main':  ('EEF2F3', ['FFEEF2F3', 'FFF2F5F6', 'FFF0F0F0']),
    't_value': ('C6CED2', ['FFC6CED2']),
    't_label': ('7D8A90', ['FF7D8A90', 'FF77848A', 'FF8C989E', 'FFA3AFB4', 'FFA0A0A0']),
    'accent':  ('65E18D', ['FF65E18D']),
    'warn':    ('F2C46D', ['FFF2C46D']),
}
# separately adjustable panel texts: token (= setting prefix) -> default colour
TEXT_EXTRA = {
    'tx_title':   'F2F5F6',   # column titles (Input / Processing / Output)
    'tx_head1':   'EEF2F3',   # column header, line 1
    'tx_head2':   '8C989E',   # column header, line 2
    'tx_section': 'A3AFB4',   # section titles (VIDEO, AUDIO ...)
    'tx_value':   'EEF2F3',   # values (right-hand column)
}
# background: token -> (setting prefix, default colour, default opacity %)
BACKGROUNDS = {
    'bg_main':  ('bg_main', '101518', 50),
    'bg_card':  ('bg_card', '1C2327', 100),
    'bg_modes': ('bg_modes', '1A2123', 100),
}


def log(msg, level=xbmc.LOGINFO):
    xbmc.log('[service.cb1.ppi] ' + msg, level)


def _hex(value):
    v = (value or '').strip().lstrip('#').upper()
    return v if re.fullmatch(r'[0-9A-F]{6}|[0-9A-F]{8}', v) else ''


def _argb(rgb_or_argb, alpha=0xFF):
    return rgb_or_argb if len(rgb_or_argb) == 8 else '%02X%s' % (alpha, rgb_or_argb)


def _pick(prefix, default):
    custom = _hex(ADDON.getSetting(prefix + '_custom'))
    if custom:
        return custom
    return _hex(ADDON.getSetting(prefix)) or default


def colour_map():
    m = {}
    for role, (default, originals) in TEXT_ROLES.items():
        v = _pick(role, default)
        for orig in originals:
            m['c_' + orig] = orig if v == default else _argb(v)
    for token, (prefix, default, pct) in BACKGROUNDS.items():
        v = _pick(prefix + '_color', default)
        try:
            p = int(ADDON.getSetting(prefix + '_alpha'))
        except ValueError:
            p = pct
        m[token] = _argb(v, round(max(0, min(100, p)) * 255 / 100))
    m['hl'] = _argb(_pick('hl_color', '12A0C7'))
    for token, default in TEXT_EXTRA.items():
        m[token] = _argb(_pick(token, default))
    return m


def lang():
    """'hu' or 'en': the 'lang' setting (auto = Kodi UI language, Hungarian only if it is Hungarian)."""
    v = ADDON.getSetting('lang')
    if v in ('1', 'en'):
        return 'en'
    if v in ('2', 'hu'):
        return 'hu'
    try:
        return 'hu' if xbmc.getLanguage(xbmc.ISO_639_1) == 'hu' else 'en'
    except Exception:
        return 'en'


def T(text):
    """Label of the mobile-app server in the chosen language (source text is Hungarian)."""
    return strings_en.APP.get(text, text) if lang() == 'en' else text


def _translate_panel(data):
    """The template is written in Hungarian; replace whole attribute/element values with English."""
    if lang() != 'en':
        return data
    for hu in sorted(strings_en.PANEL, key=len, reverse=True):
        en = strings_en.PANEL[hu]
        data = data.replace('"%s"' % hu, '"%s"' % en).replace('>%s<' % hu, '>%s<' % en)
    return data


def generate():
    """Build media/cb1 XML files from template/cb1 using the current settings."""
    if not os.path.isdir(TPL):
        log('template/cb1 is missing: nothing to generate', xbmc.LOGWARNING)
        return
    cm = colour_map()
    os.makedirs(OUT, exist_ok=True)
    for name in os.listdir(TPL):
        with open(os.path.join(TPL, name), encoding='utf-8') as f:
            data = f.read()
        data = re.sub(r'@@([A-Za-z0-9_]+)@@', lambda mo: cm.get(mo.group(1), mo.group(0)), data)
        data = _translate_panel(data)
        with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
            f.write(data)
    log('generated: ' + ', '.join('%s=%s' % kv for kv in sorted(cm.items()) if not kv[0].startswith('c_')))
