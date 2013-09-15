"""General i18n utility functions."""

import os
import urllib
import re

from htmlentitydefs import name2codepoint

import cherrypy

from gearshift import config
from gearshift.release import version as tg_version
from gearshift.util import parse_http_accept_header, request_available

_entity_re = None
_google_translation_re = None

class GoogleError(Exception):
    def __init__(self, value, response=None):
        self.response = response
        super(GoogleError, self).__init__(value)

def _repl_func(match):
    if match.group(1): # Numeric character reference
        return unichr(int(match.group(2)))
    else:
        return unichr(name2codepoint[match.group(3)])

def decode_html_entities(s, repetitions=1):
    """Replace HTML entity references in s with their unicode representation.

    If 'repetitions' is > 1, do the translation process 'repetitions' times
    feeding the output form the previous translation as the input to the next.

    Returns a unicode object.

    """
    global _entity_re
    if _entity_re is None:
        _entity_re = re.compile(r'&(?:(#)(\d+)|([^;]+));')
    
    result = s
    for i in xrange(repetitions):
        result = _entity_re.sub(_repl_func, result)
    return result

def google_translate(from_lang, to_lang, text):
    """Translate text via the translate.google.com service.

    The source language is given by 'from_lang' and the target language as
    'to_lang'. 'text' must be a unicode or UTF-8 encoded string.

    """
    class TGURLopener(urllib.FancyURLopener):
        version = "GearShift/%s" % tg_version

    global _google_translation_re
    if _google_translation_re is None:
        _google_translation_re = re.compile(
            '<textarea name=[\'"]?utrans[\'"]?.*?>(.*?)</textarea>',
            re.DOTALL | re.IGNORECASE)

    if isinstance(text, unicode):
        text = text.encode('utf-8')
    params = urllib.urlencode({
        "langpair":"%s|%s" % (from_lang, to_lang),
        "text": text,
        "ie":"UTF8",
        "oe":"UTF8"
    })

    resp = TGURLopener().open("http://translate.google.com/translate_t", params)
    s = resp.read()

    match = _google_translation_re.search(s)
    if not match:
        raise GoogleError(
            'Received invalid response from translate.google.com', response=s)

    data = match.groups()[0]
    return decode_html_entities(unicode(data, "utf-8").strip(), 2)

def lang_in_gettext_format(lang):
    if len(lang) > 2:
        country = lang[3:].upper()
        lang = lang[:2] + "_" + country
    return lang

def get_accept_languages(accept):
    """Returns a list of languages, by order of preference, based on an
    HTTP Accept-Language string.See W3C RFC 2616
    (http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html) for specification.
    """
    langs = parse_http_accept_header(accept)
    for index, lang in enumerate(langs):
        langs[index] = lang_in_gettext_format(lang)
    return langs

def get_locale(locale=None):
    """
    Returns user locale, using _get_locale or app-specific locale lookup function.
    """
    if not locale:
        get_locale_f = config.get("i18n.get_locale", _get_locale)
        locale = get_locale_f()
    return locale

def _get_locale():
    """Default function for returning locale. First looks in session for locale key,
    then checks the HTTP Accept-Language header, and finally checks the config default
    locale setting. This can be replaced by your own function by setting cherrypy
    config setting i18n.get_locale to your function name.
    """
    if not request_available():
        return config.get("i18n.default_locale", "en")

    if config.get("tools.sessions.on", False):
        locale_key = config.get("i18n.session_key", "locale")
        locale = cherrypy.session.get(locale_key)
        if locale:
            return locale
    browser_accept_lang = _get_locale_from_accept_header()
    return browser_accept_lang or config.get("i18n.default_locale", "en")

def _get_locale_from_accept_header():
    """
    Checks HTTP Accept-Language header to find preferred language if any.
    """
    try:
        header = cherrypy.request.headers.get("Accept-Language")
        if header:
            accept_languages = get_accept_languages(header)
            if accept_languages:
                return accept_languages[0]
    except AttributeError:
        pass

def set_session_locale(locale):
    """
    Sets the i18n session locale.

    Raises an error if session support is not enabled.
    """
    sess_key = config.get("i18n.session_key", "locale")
    setattr(cherrypy.session, 'sess_key', locale)
