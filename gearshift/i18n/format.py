"""Localized formatting functions.

Most if the old TurboGears i18n API has been replaced with Babel. For more
info see: http://babel.edgewall.org. You also probably want to use Babel 
directly instead of this file.

"""

import babel
from babel import Locale

import babel.dates
from babel.dates import LC_TIME, format_date, format_datetime, get_date_format, \
    get_day_names, get_month_names

import babel.numbers
from babel.numbers import format_currency, format_number, format_decimal, \
    get_decimal_symbol, get_group_symbol

from gearshift.i18n.utils import get_locale as util_get_locale

locales = None # For caching of supported locales

def get_locale(locale=None):
    global locales
    
    if locales is None:
        locales = babel.localedata.list()

    locale = util_get_locale(locale)
    return babel.negotiate_locale([locale, 'en'], locales)

def get_countries(locale=None):
    """Get all supported countries.

    Returns a list of tuples, consisting of international country code
    and localized name, e.g. ('AU', 'Australia').

    """
    locale = Locale.parse(locale or get_locale())
    countries = [item for item in locale.territories.items() if item[0].isalpha()]
    countries.sort(key=lambda x: x[1])

def get_country(key, locale=None):
    """Get localized name of country based on international country code."""

    locale = Locale.parse(locale)        
    countries = [item for item in locale.territories.items() if item[0].isalpha()]
    return countries[key]

def get_languages(locale=None):
    """Get all supported languages.

    Returns a list of tuples, with language code and localized name,
    e.g. ('en', 'English').

    """
    global locales
    
    if locales is None:
        locales = babel.localedata.list()
    
    if not locale:
        locale = get_locale()
        
    languages = [(locale, Locale.parse(locale).display_name) for locale in locales]
    languages.sort(key=lambda x: x[1])
    return languages

def get_language(key, locale=None):
    """Get localized name of language based on language code."""
    return Locale.parse(locale).display_name.capitalize()

def get_abbr_month_names(locale=LC_TIME):
    """Get list of abbreviated month names, starting with Jan."""
    return get_month_names(width='abbreviated', locale=locale)

def get_weekday_names(locale=LC_TIME):
    """Get list of full weekday names."""
    return get_day_names(width='wide', locale=locale)

def get_abbr_weekday_names(locale=LC_TIME):
    """Get list of abbreviated weekday names."""
    try:
        return get_day_names(width='abbreviated', locale=locale)
    except babel.UnknownLocaleError:
        return []

def get_decimal_format(locale=LC_TIME):
    """Get decimal point for the locale."""
    return get_decimal_symbol(locale)

def get_group_format(locale=LC_TIME):
    """Get digit group separator for thousands for the locale."""
    return get_group_symbol(locale)
    
def parse_number(value, locale=None):
    return babel.numbers.parse_number(value, locale or get_locale())

def parse_decimal(value, locale=None):
    return babel.numbers.parse_decimal(value, locale or get_locale())

def format_datetime(d, format="medium", locale=None):
    locale=locale or get_locale()
    return babel.dates.format_datetime(d, format, locale=locale)

def format_date(d, format="medium", locale=None):
    locale = locale or get_locale()
    return babel.dates.format_date(d, format, locale=locale)
