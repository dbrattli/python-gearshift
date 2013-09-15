from gearshift import validators

def test_booleanstrings():
    """'False', 'false', 'True', 'true' should be proper boolean values"""
    b = validators.StringBoolean(if_empty=False)
    assert 'false' == b.from_python(False)
    assert 'true' == b.from_python(True)
    assert 'false' == b.from_python(0)
    assert 'true' == b.from_python(1)
    assert b.to_python("True") is True
    assert b.to_python("False") is False
    assert b.to_python("true") is True
    assert b.to_python("false") is False
    assert b.to_python("") is False
    assert b.to_python(None) is False
    try:
        b.to_python("foobar")
        assert False, "random strings should fail validation"
    except validators.Invalid:
        pass

def test_datetimeconverter():
    import datetime
    date = datetime.datetime(2005,11,22,18,22)
    dt  = validators.DateTimeConverter()
    assert date == dt.to_python(date), "Accepts datetime OK"
    assert date == dt.to_python(dt.from_python(date)), "Good datetime passes validation"
    try:
        dt.to_python("foo")
        assert False, "random strings should fail validation"
    except validators.Invalid:
        pass

def test_jsonvalidator():
    v = validators.JSONValidator()
    origlist = ["Foo", "Bar", "Baz"]
    json = v.from_python(origlist)
    assert json == '["Foo", "Bar", "Baz"]'
    jsonlist = v.to_python(json)
    assert origlist == jsonlist

def test_unicodestring_validator():
    v = validators.UnicodeString()
    assert u'TurboGears' == v.to_python('TurboGears')
    assert 'TurboGears' == v.from_python('TurboGears')
    v = validators.UnicodeString(inputEncoding='cp1251')
    assert repr(v.to_python('\xf0\xf3\xeb\xe8\xf2')) == \
            "u'\u0440\u0443\u043b\u0438\u0442'"
    assert v.from_python(u'\u0440\u0443\u043b\u0438\u0442') == \
        '\xd1\x80\xd1\x83\xd0\xbb\xd0\xb8\xd1\x82' # in utf-8 encoding
    v = validators.UnicodeString()
    try:
        # feed cp1251 encoded data when utf8 is expected
        print repr(v.to_python('\xf0\xf3\xeb\xe8\xf2'))
        assert 0, 'malformed data not detected'
    except validators.Invalid:
        pass

def test_number_validador():
    assert validators.Number.to_python("45") == 45
    # test for ticket #955
    assert validators.Number.to_python(45) == 45

def test_empty_field_storage():
    from cgi import FieldStorage
    empty_field_storage = FieldStorage()
    try:
        v = validators.FieldStorageUploadConverter(
            not_empty=True).to_python(empty_field_storage)
    except validators.Invalid:
        v = None
    assert v is None, 'mandatory filename not ensured'
    # test for ticket #1705
    try:
        v = validators.FieldStorageUploadConverter(
            not_empty=False).to_python(empty_field_storage)
    except validators.Invalid:
        v = None
    assert v is empty_field_storage, 'optional filename not validated'
