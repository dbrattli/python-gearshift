"""Convenient access to an SQLObject or SQLAlchemy managed database."""

import sys
import time
import logging

import cherrypy
from cherrypy import request

try:
    from zope.sqlalchemy import ZopeTransactionExtension
    import transaction as zope_transaction
    have_transactions = True
except ImportError:
    have_transactions = False

import sqlalchemy, sqlalchemy.orm
from sqlalchemy import MetaData
from sqlalchemy.orm import scoped_session, sessionmaker
have_sqlalchemy = True

from gearshift import config
from gearshift.util import remove_keys

log = logging.getLogger("gearshift.database")

_using_sa = False

# Provide support for SQLAlchemy
if have_sqlalchemy:

    def get_engine(pkg=None):
        """Retrieve the engine based on the current configuration."""
        bind_metadata()
        return get_metadata(pkg).bind

    def get_metadata(pkg=None):
        """Retrieve the metadata for the specified package."""
        try:
            return _metadatas[pkg]
        except KeyError:
            _metadatas[pkg] = MetaData()
            return _metadatas[pkg]

    def bind_metadata():
        """Connect SQLAlchemy to the configured database(s)."""
        if metadata.is_bound():
            return

        alch_args = dict()
        for k, v in config.items():
            if "sqlalchemy" in k:
                alch_args[k.split(".")[-1]] = v

        dburi = alch_args.pop('dburi')
        if not dburi:
            raise KeyError("No sqlalchemy database config found!")
        metadata.bind = sqlalchemy.create_engine(dburi, **alch_args)

        global _using_sa
        _using_sa = True

        for k, v in config.items():
            if ".dburi" in k and 'sqlalchemy.' not in k:
                get_metadata(k.split(".")[0]).bind = sqlalchemy.create_engine(v, **alch_args)

    def create_session():
        """Create a session that uses the engine from thread-local metadata.

        The session by default does not begin a transaction, and requires that
        flush() be called explicitly in order to persist results to the database.

        """
        if not metadata.is_bound():
            bind_metadata()
        return sqlalchemy.orm.create_session()

    try:
        if have_transactions:
            maker = sessionmaker(autoflush=True, autocommit=False,
                                 extension=ZopeTransactionExtension())
            session = sqlalchemy.orm.scoped_session(maker)
        else:
            session = sqlalchemy.orm.scoped_session(create_session)
        mapper = session.mapper
    except AttributeError: # SQLAlchemy < 0.4
        from sqlalchemy.ext.sessioncontext import SessionContext
        class Objectstore(object):
            def __init__(self, *args, **kwargs):
                self.context = SessionContext(*args, **kwargs)
            def __getattr__(self, name):
                return getattr(self.context.current, name)
            def begin(self):
                self.create_transaction()
            def commit(self):
                if self.transaction:
                    self.transaction.commit()
            def rollback(self):
                if self.transaction:
                    self.transaction.rollback()
        session = Objectstore(create_session)
        context = session.context
        Query = sqlalchemy.Query
        from sqlalchemy.orm import mapper as orm_mapper
        def mapper(cls, *args, **kwargs):
            validate = kwargs.pop('validate', False)
            if not hasattr(getattr(cls, '__init__'), 'im_func'):
                def __init__(self, **kwargs):
                     for key, value in kwargs.items():
                         if validate and key not in self.mapper.props:
                             raise KeyError(
                                "Property does not exist: '%s'" % key)
                         setattr(self, key, value)
                cls.__init__ = __init__
            m = orm_mapper(cls, extension=context.mapper_extension,
                *args, **kwargs)
            class query_property(object):
                def __get__(self, instance, cls):
                    return Query(cls, session=context.current)
            cls.query = query_property()
            return m

    _metadatas = {}
    _metadatas[None] = MetaData()
    metadata = _metadatas[None]

    try:
        import elixir
        elixir.metadata, elixir.session = metadata, session
    except ImportError:
        pass

else:
    def get_engine():
        pass
    def get_metadata():
        pass
    def bind_metadata():
        pass
    def create_session():
        pass
    session = metadata = mapper = None

bind_meta_data = bind_metadata # deprecated, for backward compatibility


def set_db_uri(dburi, package=None):
    """Sets the database URI to use either globally or for a specific
    package. Note that once the database is accessed, calling
    setDBUri will have no effect.

    @param dburi: database URI to use
    @param package: package name this applies to, or None to set the default.
    """
    if package:
        config.update({"%s.dburi" % package : dburi})
    else:
        config.update({"sqlobject.dburi" : dburi})

def restart_transaction(args):
    if have_transactions:
        zope_transaction.begin()

def _use_sa(args=None):
##    print "_use_sa: %s" % _using_sa
    return _using_sa

def dispatch_exception(exception, args, kw):
    # errorhandling import here to avoid circular imports
    from gearshift.errorhandling import dispatch_error
    # Keep in mind func is not the real func but _expose
    real_func, accept, allow_json, controller = args[:4]
    args = args[4:]
    exc_type, exc_value, exc_trace = sys.exc_info()
    remove_keys(kw, ("tg_source", "tg_errors", "tg_exceptions"))
    try:
        output = dispatch_error(
            controller, real_func, None, exception, *args, **kw)
    except NoApplicableMethods:
        raise exc_type, exc_value, exc_trace
    else:
        del exc_trace
        return output

def sa_transaction_active():
    """Check whether SA transaction is still active."""
    try:
        return session().is_active
    except (TypeError, AttributeError): # SA < 0.4.7
        try:
            transaction = request.sa_transaction
        except AttributeError:
            return False
        try:
            return transaction and transaction.is_active
        except AttributeError: # SA < 0.4.3
            return transaction.session.transaction

def EndTransactions():
    if _use_sa():
        session.clear()
    end_all()

__all__ = ["metadata", "session", "mapper",
           "get_engine", "get_metadata", "bind_metadata", "create_session",
           "PackageHub", "AutoConnectHub", "set_db_uri",
           "commit_all", "rollback_all", "end_all", "so_to_dict",
           "so_columns", "so_joins", "EndTransactions"]
