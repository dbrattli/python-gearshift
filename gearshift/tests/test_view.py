# -*- coding: utf-8 -*-

from gearshift import view, config
import unittest


class TestView(unittest.TestCase):

    def setUp(self):
        #if not view.engines:
        #    view.load_engines()
        pass

    def test_cycle(self):
        oe = view.base.cycle(('odd','even'))
        assert str(oe) == str(None)
        assert oe.next() == 'odd'
        assert str(oe) == 'odd'
        assert oe.next() == 'even'
        assert oe.value == 'even'
        assert oe.next() == 'odd'
        assert oe.value == 'odd'

    def test_selector(self):
        assert view.base.selector(False) is None
        assert view.base.selector(True) == 'selected'

    def test_checker(self):
        assert view.base.checker(False) is None
        assert view.base.checker(True) == 'checked'

    def test_ipeek(self):
        seq = xrange(3, 6)
        assert view.base.ipeek(seq)
        assert list(seq) == range(3, 6)
        seq = xrange(3, 3)
        assert not view.base.ipeek(seq)
        assert list(seq) == []

    def test_UnicodeValueAppearingInATemplateIsFine(self):
        ustr = u"micro-eXtreme Programming ( µ XP): Embedding XP Within Standard Projects"
        info = dict(someval=ustr)
        val = view.render(info, template="gearshift.tests.simple")
        self.failUnless(u"Paging all " + ustr in val.decode("utf-8"))

    def test_templateRetrievalByPath(self):
        config.update({'server.environment' : 'development'})
        from turbokid import kidsupport
        ks = kidsupport.KidSupport()
        cls = ks.load_template("gearshift.tests.simple")
        assert cls is not None
        t = cls()
        t.someval = "hello"
        filled = str(t)
        assert "groovy" in filled
        assert "html" in filled
        # the following import should not fail, if everything is working correctly:
        import gearshift.tests.simple

    def test_default_output_encoding(self):
        info = dict(someval="someval")
        template = "gearshift.tests.simple"
        headers = {}
        # default encoding is utf-8
        val = view.render(info, template, headers=headers)
        assert headers.get('Content-Type') == 'text/html; charset=utf-8'
        # encoding can be changed and will be added to existing content type
        try:
            config.update({'kid.encoding': 'iso-8859-1'})
            headers['Content-Type'] = 'text/html'
            view.render(info, template, headers=headers)
            assert headers.get('Content-Type') == 'text/html; charset=iso-8859-1'
        finally:
            config.update({'kid.encoding': 'utf-8'})

    def test_content_types(self):
        info = dict(someval="someval")
        template = "gearshift.tests.simple"
        headers = {}
        view.render(info, template, headers=headers)
        assert headers.get('Content-Type') == 'text/html; charset=utf-8'
        headers = {}
        view.render(info, template, headers=headers, format='html')
        assert headers.get('Content-Type') == 'text/html; charset=utf-8'
        headers = {}
        view.render(info, template, headers=headers, format='html-strict')
        assert headers.get('Content-Type') == 'text/html; charset=utf-8'
        headers = {}
        view.render(info, template, headers=headers, format='xhtml')
        assert headers.get('Content-Type') == 'text/html; charset=utf-8'
        headers = {}
        view.render(info, template, headers=headers, format='xhtml-strict')
        assert headers.get('Content-Type') == 'text/html; charset=utf-8'
        headers = {}
        view.render(info, template, headers=headers, format='xml')
        assert headers.get('Content-Type') == 'text/xml; charset=utf-8'
        headers = {}
        view.render(info, template, headers=headers, format='json')
        assert headers.get('Content-Type') == 'application/json'
        config.update({'global':
            {'tg.format_mime_types': {'xhtml': 'application/xhtml+xml'}}})
        headers = {}
        view.render(info, template, headers=headers, format='xhtml')
        assert headers.get('Content-Type') == 'application/xhtml+xml; charset=utf-8'
        headers = {}
        view.render(info, template, headers=headers, format='xhtml-strict')
        assert headers.get('Content-Type') == 'application/xhtml+xml; charset=utf-8'
        config.update({'global': {'tg.format_mime_types': {}}})

    def test_plain_format(self):
        info = dict(someval="dumbos")
        template = "gearshift.tests.simple"
        headers = {}
        plain = view.render(info, template, headers=headers, format='plain')
        assert headers.get('Content-Type') == 'text/plain; charset=utf-8'
        assert plain.strip() == ('This is the groovy test template.'
            ' Paging all dumbos.')
        headers = {}
        text = view.render(info, template, headers=headers, format='text')
        assert headers.get('Content-Type') == 'text/plain; charset=utf-8'
        assert text == plain
        try:
            view.render(info, template, headers=headers, format='dumbo')
        except KeyError:
            pass
        else:
            assert False, "'dumbo' should not be accepted as format"
