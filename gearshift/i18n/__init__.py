"""
TurboGears internationalization/localization module.
"""

from gearshift.i18n.tg_gettext import gettext, ngettext, install, \
    is_locale_supported, lazy_gettext, lazy_ngettext, plain_gettext, \
    dummy_, dummy_gettext
from gearshift.i18n.utils import get_locale, get_accept_languages, \
    set_session_locale, google_translate
from gearshift.i18n.format import get_countries, get_country, \
    get_month_names, get_abbr_month_names, get_weekday_names, \
    get_abbr_weekday_names, get_languages, format_date, format_datetime, \
    format_number, \
    format_decimal, format_currency, parse_number, parse_decimal
