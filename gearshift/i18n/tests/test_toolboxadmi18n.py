# -*- coding: utf-8 -*-

from gearshift.toolbox.admi18n import pygettext

def test_support_explicit_lang():
    """the coma should not make the extractor bork
    """
    assert _('Something', 'en') == u'Something'
    assert _('New', 'en') == u'New'
