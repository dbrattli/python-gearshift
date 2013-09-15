
import os.path

from gearshift import config
from gearshift.i18n import sogettext

def setup_module():
    basedir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "tests")
    locale_dir = os.path.join(basedir, 'locale')
    config.update({
        'i18n.locale_dir': locale_dir,
        'i18n.domain': 'messages',
        'i18n.default_locale': 'en',
        'i18n.get_locale': lambda: 'en',
        'i18n.run_template_filter': False,
        'sqlobject.dburi': "sqlite:///:memory:"
    })
    sogettext.create_so_catalog(["en", "fi"], "messages")
