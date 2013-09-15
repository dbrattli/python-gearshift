from ez_setup import use_setuptools
use_setuptools()
from setuptools import setup, find_packages
from pkg_resources import DistributionNotFound

import sys
import os

if sys.version_info < (2, 4):
    raise SystemExit("Python 2.4 or later is required")

execfile(os.path.join("gearshift", "release.py"))

# setup params
install_requires = [
    "CherryPy >= 3.1.1",
    "FormEncode >= 0.7.1",
    "Genshi >= 0.4.4",
    "simplejson >= 1.9.1",
    "configobj >= 4.5.3",
    "Babel >= 0.9.4",
]

storm = [
    "storm",
]

sqlobject = [
    "SQLObject >= 0.10.1",
]

sqlalchemy = [
    "Elixir >= 0.4.0",
    "SQLAlchemy >= 0.4.0",
]

transaction = [
    "repoze.tm2 >= 1.0a3",
    "transaction >=1.0a1",
    "zope.sqlalchemy >= 0.3"
]

widgets = [
    'ToscaWidgets',
]

markup = [
    'textile',
    'docutils',
    'markdown',
    'trac'
]

elements = [
    'elements >= 0.6.2'
]

authentication = [
    "oauth >= 1.0"
]

testtools =  [
    "nose >= 0.9.3",
    "WebTest"
]

tgtesttools =  testtools

if sys.version_info < (2, 5):
    tgtesttools.extend([
            # Python < 2.5 does not include SQLite
            "pysqlite",
            # WebTest needs a current wsgiref version
            "wsgiref >= 0.1.2",
        ])

develop_requires = (install_requires + tgtesttools + sqlalchemy +
    sqlobject + widgets + authentication + markup + elements)

setup(
    name="GearShift",
    description=description,
    long_description=long_description,
    version=version,
    author=author,
    author_email=email,
    maintainer=maintainer,
    maintainer_email=maintainer_email,
    url=url,
    download_url=download_url,
#    dependency_links=dependency_links,
    license=license,
    zip_safe=False,
    install_requires = install_requires,
    packages=find_packages(),
    include_package_data=True,
    exclude_package_data={"thirdparty": ["*"]},
    entry_points = """
    [console_scripts]
    gs-admin = gearshift.command:main

    [distutils.commands]
    docs = gearshift.docgen:GenSite

    [paste.paster_create_template]
    tgbase = gearshift.command.quickstart:BaseTemplate
    gearshift = gearshift.command.quickstart:TurbogearsTemplate
    tgbig = gearshift.command.quickstart:TGBig
    tgwidget = gearshift.command.quickstart:TGWidgetTemplate

    [gearshift.command]
    quickstart = gearshift.command.quickstart:quickstart
    sql = gearshift.command.base:SQL
    shell = gearshift.command.base:Shell
    toolbox = gearshift.command.base:ToolboxCommand
    update = gearshift.command.quickstart:update
    i18n = gearshift.command.i18n:InternationalizationTool
    info = gearshift.command.info:InfoCommand

    """,
    extras_require = {
        "storm" : storm,
        "sqlobject" : sqlobject,
        "sqlalchemy" : sqlalchemy,
        "authentication" : authentication,
        "markup" : markup,
        "widgets" : widgets,
        "elements" : elements,
        "transaction" : transaction,
        "testtools" : testtools,
        "tgtesttools" : tgtesttools,
        "develop" : develop_requires
    },
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'],
    test_suite = 'nose.collector',
)
