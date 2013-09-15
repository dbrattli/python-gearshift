import logging
import ntpath
import os
import re
import sys

from cStringIO import StringIO

import pkg_resources
import gearshift
from gearshift import testutil

rfn = pkg_resources.resource_filename
testfile = rfn(__name__, "configfile.cfg")

logout = StringIO()
logging.logout = logout

# last forward slash (the one before static) is hard coded in our config
# file... all other path separators are calculated platform wise...

def test_update_from_package():
    gearshift.update_config(modulename="gearshift.tests.config")
    assert gearshift.config.get("foo.bar") == "BAZ!"
    print gearshift.config.get("my.static")
    assert gearshift.config.get("my.static").endswith(
            "gearshift%stests/static" % os.path.sep)
    assert gearshift.config.app["/static"]["tools.staticdir.on"] == True

def test_update_from_both():
    gearshift.update_config(configfile = testfile,
        modulename="gearshift.tests.config")
    print gearshift.config.get("foo.bar")
    assert gearshift.config.get("foo.bar") == "blurb"
    assert gearshift.config.get("tg.something") == 10
    print gearshift.config.get("test.dir")
    assert gearshift.config.get("test.dir").endswith(
        "gearshift%stests" % os.path.sep)

callnum = 0

def windows_filename(*args, **kw):
    """Small helper function to emulate pkg_resources.resource_filename
    as if it was called on a Wwindows system even if the tester is in fact
    using Linux or Mac OS X.

    We need to keep track how often the function was called, since
    'gearshift.update_config' calls 'pkg_resources.resource_filename' at least
    twice and we only want to return the fake Windows path the second and
    following times.

    """
    global callnum
    callnum += 1
    if callnum > 1:
        return "c:\\foo\\bar\\"
    else:
        return rfn(*args, **kw)

def test_update_on_windows():
    """gearshift.update_config works as we intend on Windows.
    """
    # save the original function
    orig_resource_fn = pkg_resources.resource_filename
    # monkey patch pkg resources to emulate windows
    pkg_resources.resource_filename = windows_filename

    gearshift.update_config(configfile=testfile,
        modulename="gearshift.tests.config")
    testdir = gearshift.config.get("test.dir")
    # update_config calls os.normpath on package_dir, but this will have no
    # effect on non-windows systems, so we call ntpath.normpath on those here
    if not sys.platform.startswith('win'):
        testdir = ntpath.normpath(testdir)

    # restore original function
    pkg_resources.resource_filename = orig_resource_fn
    assert testdir == "c:\\foo\\bar"

def test_logging_config():
    logout.truncate(0)
    log = logging.getLogger("gearshift.tests.test_config.logconfig")
    log.info("Testing")
    logged = logout.getvalue()
    print "Logged: %s" % logged
    assert re.match(r'F1 \d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d,\d\d\d INFO '
                    'Testing', logged)
    assert gearshift.config.get("tg.new_style_logging", False)
