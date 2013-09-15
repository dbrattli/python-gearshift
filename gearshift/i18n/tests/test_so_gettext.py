
import gearshift
from gearshift.i18n import sogettext
from gearshift.i18n.tg_gettext import tg_gettext
from gearshift.i18n.tests import setup_module as basic_setup_module

from gearshift.i18n.tests.test_tg_gettext import test_gettext, test_ngettext
from gearshift.i18n.tests.test_tg_gettext import test_invalid_domain
from gearshift.i18n.tests.test_kidutils import test_match_template, test_i18n_filter

def setup_module(): 
    gearshift.config.update({"i18n.gettext":sogettext.so_gettext})
    basic_setup_module()

def teardown_module(): 
    gearshift.config.update({"i18n.gettext":tg_gettext})

def test_so_gettext():
    test_gettext()
    test_ngettext()
    test_match_template()
    test_i18n_filter()
    test_invalid_domain()

