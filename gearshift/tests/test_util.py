
import sys
from StringIO import StringIO

from gearshift import config, util


def test_deprecated():

    @util.deprecated('this is old')
    def some_old_function(x, y):
        """some old function"""
        return x + y

    assert "some old function" in some_old_function.__doc__
    some_old_function.__name__ == 'some_old_function'

    stderr, sys.stderr = sys.stderr, StringIO()
    try:
        assert some_old_function(1, 2) == 3
    finally:
        stderr, sys.stderr = sys.stderr, stderr
    assert 'DeprecationWarning: this is old' in stderr.getvalue()
    stderr.close()

    # Deprecation warnings should only be emitted once.
    stderr, sys.stderr = sys.stderr, StringIO()
    try:
        assert some_old_function(2, 3) == 5
    finally:
        stderr, sys.stderr = sys.stderr, stderr
    assert 'DeprecationWarning: this is old' not in stderr.getvalue()
    stderr.close()


def test_call_on_stack():

    def recurse(level):
        if level:
            return recurse(level-1)
        return util.call_on_stack('recurse', dict())

    assert not recurse(0)
    assert recurse(1)

    def recurse(level, arg=None):
        if level:
            return recurse(level-1, arg)
        return util.call_on_stack('recurse', dict(arg='true'), 3)

    assert not recurse(3, 'true')
    assert recurse(4, 'true')
    assert not recurse(4, 'false')


def test_remove_keys():

    assert util.remove_keys(dict(x=1, y=2, z=3), 'xz') == dict(y=2)


def test_has_arg():

    def fun(x, z=2):
        pass

    assert util.has_arg(fun, 'x')
    assert not util.has_arg(fun, 'y')
    assert util.has_arg(fun, 'z')


def test_arg_index():

    def fun(a, b, y=3, z=4):
        pass

    assert util.arg_index(fun, 'a') == 0
    assert util.arg_index(fun, 'b') == 1
    assert util.arg_index(fun, 'c') is None
    assert util.arg_index(fun, 'y') == 2
    assert util.arg_index(fun, 'z') == 3


def test_parse_http_accept_header():
    t = util.parse_http_accept_header
    assert t(None) == []
    assert t('') == []
    assert t('text/html') == ['text/html']
    assert t('text/html;level=1') == ['text/html;level=1']
    assert t(' text/html; level=1 ') == ['text/html; level=1']
    assert t('audio/*, audio/mid') == ['audio/*', 'audio/mid']
    assert t('audio/*; q=0.2, audio/mid') == ['audio/mid', 'audio/*']
    assert t('audio/*; q=0.2, audio/mid; q=0.3') == ['audio/mid', 'audio/*']
    assert t('audio/*; q=0.3, audio/mid; q=0.2') == ['audio/*', 'audio/mid']
    assert t('audio/*, audio/mid; q=0.2') == ['audio/*', 'audio/mid']
    assert t('audio/*, audio/mid; q=0') == ['audio/*']
    assert t('''text/plain; q=0.5, text/html,
        text/x-dvi; q=0.8, text/x-c''') == ['text/html', 'text/x-c',
            'text/x-dvi', 'text/plain']
    assert t('''text/*;q=0.3, text/html;q=0.7, text/html;level=1,
        text/html;level=2;q=0.4, */*;q=0.5''') == ['text/html;level=1',
            'text/html', '*/*', 'text/html;level=2', 'text/*']
    assert t('compress;q=0.5, gzip;q=1.0') == ['gzip', 'compress']
    assert t('gzip;q=1.0, identity; q=0.5, *;q=0') == ['gzip', 'identity']
    assert t('da, en-gb;q=0.8, en;q=0.7') == ['da', 'en-gb', 'en']
    assert t('da, en-gb;q=0.7, en;q=0.8') == ['da', 'en', 'en-gb']
    assert t('da;q=0.75, en-gb;q=0.099, en;q=0.8') == ['en', 'da', 'en-gb']


def test_preferred_from_http_accept_header():
    t = util.simplify_http_accept_header
    assert t(None) is None
    assert t('') == ''
    assert t('text/html') == 'text/html'
    assert t('text/html;level=1') == 'text/html'
    assert t(' text/html; level=1 ') == 'text/html'
    assert t('audio/*, audio/mid') == 'audio/*'
    assert t('audio/*; q=0.2, audio/mid') == 'audio/mid'
    assert t('audio/*; q=0.2, audio/mid; q=0.3') == 'audio/mid'
    assert t('audio/*; q=0.3, audio/mid; q=0.2') == 'audio/*'
    assert t('audio/*, audio/mid; q=0.2') == 'audio/*'
    assert t('audio/*, audio/mid; q=0') == 'audio/*'
    assert t('''text/plain; q=0.5, text/html,
        text/x-dvi; q=0.8, text/x-c''') == 'text/html'
    assert t('''text/*;q=0.3, text/html;q=0.7, text/html;level=1,
        text/html;level=2;q=0.4, */*;q=0.5''') == 'text/html'
    assert t('''text/*;q=0.3, text/plain;q=0.7, text/html;level=1,
        text/sgml;q=0.4, */*;q=0.5''') == 'text/html'
    assert t('''text/*;q=0.3, text/plain;q=0.7, text/html;level=1;q=0.6,
        text/sgml;q=0.4, */*;q=0.5''') == 'text/plain'
    assert t('compress;q=0.5, gzip;q=1.0') == 'gzip'
    assert t('gzip;q=1.0, identity; q=0.5, *;q=0') == 'gzip'
    assert t('da, en-gb;q=0.8, en;q=0.7') == 'da'
    assert t('da, en-gb;q=0.7, en;q=0.8') == 'da'
    assert t('da;q=0.75, en-gb;q=0.099, en;q=0.8') == 'en'


def test_quote_cookie():
    assert util.quote_cookie ('Hello, W\xf6rld') \
        == 'Hello%2C%20W\xf6rld'
    assert util.quote_cookie ('$1;\tinsert coin!') \
        == '%241%3B%09insert%20coin!'


def test_get_template_encoding_default():
    assert util.get_template_encoding_default() == 'utf-8'


def test_get_mime_type_for_format():
    assert util.get_mime_type_for_format('plain') == 'text/plain'
    assert util.get_mime_type_for_format('text') == 'text/plain'
    assert util.get_mime_type_for_format('html') == 'text/html'
    assert util.get_mime_type_for_format('xhtml') == 'text/html'
    assert util.get_mime_type_for_format('xml') == 'text/xml'
    assert util.get_mime_type_for_format('json') == 'application/json'
    assert util.get_mime_type_for_format('foo') == 'text/html'
    config.update({'global': {'tg.format_mime_types':
        {'xhtml': 'application/xhtml+xml', 'foo': 'text/bar'}}})
    assert util.get_mime_type_for_format('xhtml') == 'application/xhtml+xml'
    assert util.get_mime_type_for_format('json') == 'application/json'
    assert util.get_mime_type_for_format('foo') == 'text/bar'
    config.update({'global': {'tg.format_mime_types': {}}})
    assert util.get_mime_type_for_format('xhtml') == 'text/html'
    assert util.get_mime_type_for_format('foo') == 'text/html'


def test_mime_type_has_charset():
    assert not util.mime_type_has_charset(None)
    assert not util.mime_type_has_charset('foo/bar')
    assert util.mime_type_has_charset('text/foobar')
    assert util.mime_type_has_charset('application/xml')
    assert util.mime_type_has_charset('application/foo+xml')
    assert util.mime_type_has_charset('application/javascript')
    assert not util.mime_type_has_charset('application/foobar')
    assert not util.mime_type_has_charset('application/json')


def test_get_template_encoding_default():
    assert util.get_template_encoding_default() == 'utf-8'


def test_get_mime_type_for_format():
    assert util.get_mime_type_for_format('plain') == 'text/plain'
    assert util.get_mime_type_for_format('text') == 'text/plain'
    assert util.get_mime_type_for_format('html') == 'text/html'
    assert util.get_mime_type_for_format('xhtml') == 'text/html'
    assert util.get_mime_type_for_format('xml') == 'text/xml'
    assert util.get_mime_type_for_format('json') == 'application/json'
    assert util.get_mime_type_for_format('foo') == 'text/html'
    config.update({'global': {'tg.format_mime_types':
        {'xhtml': 'application/xhtml+xml', 'foo': 'text/bar'}}})
    assert util.get_mime_type_for_format('xhtml') == 'application/xhtml+xml'
    assert util.get_mime_type_for_format('json') == 'application/json'
    assert util.get_mime_type_for_format('foo') == 'text/bar'
    config.update({'global': {'tg.format_mime_types': {}}})
    assert util.get_mime_type_for_format('xhtml') == 'text/html'
    assert util.get_mime_type_for_format('foo') == 'text/html'


def test_mime_type_has_charset():
    assert not util.mime_type_has_charset(None)
    assert not util.mime_type_has_charset('foo/bar')
    assert util.mime_type_has_charset('text/foobar')
    assert util.mime_type_has_charset('application/xml')
    assert util.mime_type_has_charset('application/foo+xml')
    assert util.mime_type_has_charset('application/javascript')
    assert not util.mime_type_has_charset('application/foobar')
    assert not util.mime_type_has_charset('application/json')


def test_find_precision():
    assert util.find_precision(0) == 0
    assert util.find_precision(42) == 0
    assert util.find_precision(0.1) == 1
    assert util.find_precision(1234567.8) == 1
    assert util.find_precision(34.25) == 2
    assert util.find_precision(1234567.123) == 3
    assert util.find_precision(123.1234567) == 7


def test_copy_if_mutable():
    test_values = ((None, False),
        ('foo', False), (42, False), ((1, 2), False),
        ([1, 2], True), ({1: 2}, True))
    for value, mutable in test_values:
        if mutable:
            assert util.copy_if_mutable(value) == value
            assert util.copy_if_mutable(value) is not value
            ret = util.copy_if_mutable(value, True)
            assert ret[0] == value
            assert ret[0] is not value
            assert ret[1] is True
        else:
            assert util.copy_if_mutable(value) is value
            ret = util.copy_if_mutable(value, True)
            assert ret[0] is value
            assert ret[1] is False


def test_fixentities():
    assert util.fixentities('Chip&nbsp;&amp;&nbsp;Chap') \
        == 'Chip&#160;&amp;&#160;Chap'
    assert util.fixentities('<&quot;&lt;&copy;&gt;&quot;>') \
        == '<&quot;&lt;&#169;&gt;&quot;>'


def test_match_ip():
    m = util.match_ip
    assert m('1.2.3.4', '1.2.3.4')
    assert not m('1.2.3.4', '1.2.3.5')
    assert not m('4.3.2.1', '5.3.2.1')
    assert m('1.2.3.4', '::ffff:102:304')
    assert not m('1.2.3.4', '::102:304')
    assert m('127.0.0.1', '::ffff:127.0.0.1')
    assert m('127.0.0.1', '::ffff:7f00:0001')
    assert m('::ffff:127.0.0.1', '127.0.0.1')
    assert m('192.168.42.76/32', '192.168.42.76')
    assert m('192.168.42.77/32', '192.168.42.77')
    assert not m('192.168.42.76/32', '192.168.42.77')
    assert not m('192.168.42.77/32', '192.168.42.76')
    assert m('192.168.42.76/31', '192.168.42.76')
    assert m('192.168.42.76/31', '192.168.42.77')
    assert m('224.0.0.0/3', '224.1.2.3')
    assert m('224.0.0.0/3', '255.255.255.255')
    assert not m('224.0.0.0/3', '192.0.0.0')
    assert not m('192.168.42.76/31', '192.168.42.73')
    assert m('1:2:3::', '1:02:0003:0:0::0')
    assert m('1:2:3::/48', '1:2:3:4::')
    assert not m('1:2:3::/48', '1:2:4::')
    assert m('1:2:3::8', '1:2:3:0:0:0:0:8')
    assert m('2001:0db8:85a3:08d3:1319:8a2e:0370:7334',
        '2001:db8:85a3:8d3:1319:8a2e:3.112.115.52')
    assert m('2001:db8:85a3:8d3:1300::/72',
        '2001:0db8:85a3:08d3:1319:8a2e:0370:7334')
    assert m('2001:db8:85a3:8d3:1300::/72',
        '2001:0db8:85a3:08d3:1399:8a2e:0370:7334')
    assert not m('2001:db8:85a3:8d3:1300::/72',
        '2001:0db8:85a3:08d3:1219:8a2e:0370:7334')
