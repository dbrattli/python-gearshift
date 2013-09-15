# -*- coding: utf-8 -*-

from gearshift.i18n.utils import *

def test_get_accept_languages():
    assert get_accept_languages("da, en-gb;q=0.8, en;q=0.7") == [
        "da", "en_GB", "en"]
    assert get_accept_languages("da;q=0.6, en-gb;q=1.0, en;q=0.7") == [
        "en_GB", "en", "da"]

def test_decode_html_entities():
    assert decode_html_entities('&amp;lt;div&amp;gt;', 2) == u'<div>'
    assert decode_html_entities('&lt;div&gt;') == u'<div>'
    assert decode_html_entities('&Auml;') == u'\xc4'
    assert decode_html_entities('&amp;Auml;', 2) == u'\xc4'
