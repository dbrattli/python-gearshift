import os
from datetime import datetime

import cherrypy

import storm
from storm.locals import *

import logging
log = logging.getLogger("gearshift.identity.stprovider")

import gearshift
from gearshift import identity
from gearshift.util import load_class

def to_db_encoding(s, encoding):
    if isinstance(s, str):
        pass
    elif hasattr(s, '__unicode__'):
        s = unicode(s)
    if isinstance(s, unicode):
        s = s.encode(encoding)
    return s

# Global class references --
# these will be set when the provider is initialised.
user_class = None
group_class = None
permission_class = None
visit_class = None

class StormIdentity(object):
    """Identity that uses a model from a database (via Storm)."""

    def __init__(self, visit_key=None, user=None):
        self.visit_key = visit_key
        if user:
            self._user = user
            if visit_key is not None:
                self.login()

    @property
    def user(self):
        """Get user instance for this identity."""
        try:
            return self._user
        except AttributeError:
            # User hasn't already been set
            pass
        # Attempt to load the user. After this code executes, there *will* be
        # a _user attribute, even if the value is None.
        visit = self.visit_link
        if visit:
            store = cherrypy.thread_data.store
            self._user = store.get(user_class, visit.user_id)
        else:
            self._user = None
        return self._user

    @property
    def user_name(self):
        """Get user name of this identity."""
        if not self.user:
            return None
        return self.user.user_name

    @property
    def user_id(self):
        """Get user id of this identity."""
        if not self.user:
            return None
        return self.user.id

    @property
    def anonymous(self):
        """Return true if not logged in."""
        return not self.user

    @property
    def permissions(self):
        """Get set of permission names of this identity."""
        try:
            return self._permissions
        except AttributeError:
            # Permissions haven't been computed yet
            pass
        if not self.user:
            self._permissions = frozenset()
        else:
            self._permissions = frozenset(
                p.permission_name for p in self.user.permissions)
        return self._permissions

    @property
    def groups(self):
        """Get set of group names of this identity."""
        try:
            return self._groups
        except AttributeError:
            # Groups haven't been computed yet
            pass
        if not self.user:
            self._groups = frozenset()
        else:
            self._groups = frozenset(g.group_name for g in self.user.groups)
        return self._groups

    @property
    def group_ids(self):
        """Get set of group IDs of this identity."""
        try:
            return self._group_ids
        except AttributeError:
            # Groups haven't been computed yet
            pass
        if not self.user:
            self._group_ids = frozenset()
        else:
            self._group_ids = frozenset(g.id for g in self.user.groups)
        return self._group_ids

    @property
    def visit_link(self):
        """Get the visit link to this identity."""
        if self.visit_key is None:
            return None
        #try:
        return visit_class.by_visit_key(self.visit_key)
        #except StormNotFound:
        #    return None

    @property
    def login_url(self):
        """Get the URL for the login page."""
        return identity.get_failure_url()

    def login(self):
        """Set the link between this identity and the visit."""
        store = cherrypy.thread_data.store
        visit = self.visit_link
        if visit:
            visit.user_id = self._user.id
        else:
            visit = visit_class(visit_key=self.visit_key, user_id=self._user.id)
            store.add(visit)            

    def logout(self):
        """Remove the link between this identity and the visit."""
        store = cherrypy.thread_data.store
        
        visit = self.visit_link
        if visit:
            store.remove(visit)
        # Clear the current identity
        identity.set_current_identity(StormIdentity())


class StormIdentityProvider(object):
    """IdentityProvider that uses a model from a database (via Storm)."""

    def __init__(self):
        super(StormIdentityProvider, self).__init__()
        get = gearshift.config.get

        global user_class, group_class, permission_class, visit_class

        user_class_path = get("tools.identity.stprovider.model.user",
            __name__ + ".TG_User")
        user_class = load_class(user_class_path)
        if user_class:
            log.info("Successfully loaded \"%s\"" % user_class_path)
        try:
            self.user_class_db_encoding = \
                user_class.sqlmeta.columns['user_name'].dbEncoding
        except (KeyError, AttributeError):
            self.user_class_db_encoding = 'UTF-8'
        group_class_path = get("tools.identity.stprovider.model.group",
            __name__ + ".TG_Group")
        group_class = load_class(group_class_path)
        if group_class:
            log.info("Successfully loaded \"%s\"" % group_class_path)

        permission_class_path = get("tools.identity.stprovider.model.permission",
            __name__ + ".TG_Permission")
        permission_class = load_class(permission_class_path)
        if permission_class:
            log.info("Successfully loaded \"%s\"" % permission_class_path)

        visit_class_path = get("tools.identity.stprovider.model.visit",
            __name__ + ".TG_VisitIdentity")
        visit_class = load_class(visit_class_path)
        if visit_class:
            log.info("Successfully loaded \"%s\"" % visit_class_path)

        # Default encryption algorithm is to use plain text passwords
        algorithm = get("tools.identity.stprovider.encryption_algorithm", None)
        self.encrypt_password = lambda pw: \
            identity.encrypt_pw_with_algorithm(algorithm, pw)

    def create_provider_model(self):
        """Create the database tables if they don't already exist."""
        return

    def validate_identity(self, user_name, password, visit_key):
        """Validate the identity represented by user_name using the password.

        Must return either None if the credentials weren't valid or an object
        with the following properties:
            user_name: original user name
            user: a provider dependant object (TG_User or similar)
            groups: a set of group names
            permissions: a set of permission names

        """
        user_name = to_db_encoding(user_name, self.user_class_db_encoding)
        user = user_class.by_user_name(user_name)
        if not user:
            log.warning("No such user: %s", user_name)
            return None
            
        if not self.validate_password(user, user_name, password):
            log.info("Passwords don't match for user: %s", user_name)
            return None
        log.info("Associating user (%s) with visit (%s)", user_name, visit_key)
        return StormIdentity(visit_key, user)

    def validate_password(self, user, user_name, password):
        """Check the user_name and password against existing credentials.

        Note: user_name is not used here, but is required by external
        password validation schemes that might override this method.
        If you use StormIdentityProvider, but want to check the passwords
        against an external source (i.e. PAM, a password file, Windows domain),
        subclass StormIdentityProvider, and override this method.

        """
        salt = user.password[40:]
        if salt:
            hashed_pass = self.encrypt_password(password + salt)
            return user.password[:40] == hashed_pass
        else:
            # Old style password without salt stored in DB. 
            success = user.password == self.encrypt_password(password)
            if success:
                # Convert it to new style salted passwords
                user.password = password
            return success
    
    def load_identity(self, visit_key):
        """Lookup the principal represented by user_name.

        Return None if there is no principal for the given user ID.

        Must return an object with the following properties:
            user_name: original user name
            user: a provider dependant object (TG_User or similar)
            groups: a set of group names
            permissions: a set of permission names

        """
        return StormIdentity(visit_key)

    def anonymous_identity(self):
        """Return anonymous identity.

        Must return an object with the following properties:
            user_name: original user name
            user: a provider dependant object (TG_User or similar)
            groups: a set of group names
            permissions: a set of permission names

        """
        return StormIdentity()

    def authenticated_identity(self, user):
        """Constructs Identity object for users with no visit_key."""
        return StormIdentity(user=user)


class TG_VisitIdentity():
    """A visit to your website."""
    __storm_table__ = "tg_visit_identity"

    id = Int(primary=True)
    visit_key = Unicode()
    user_id = Int()

    @classmethod
    def by_visit_key(cls, visit_key):
        return store.find(cls, cls.visit_key == visit_key).one()

class TG_UserGroup(object):
    __storm_table__ = "tg_user_group"
    __storm_primary__ = "user_id", "group_id"
    user_id = Int()
    group_id = Int()

class TG_Group(object):
    """An ultra-simple group definition."""
    __storm_table__ = "tg_group"

    id = Int(primary=True)
    group_name = Unicode()
    display_name = Unicode()
    created = DateTime(default=datetime.now)

    # collection of all users belonging to this group
    #users = RelatedJoin("TG_User", intermediateTable="tg_user_group",
    #    joinColumn="group_id", otherColumn="user_id")
    #users = ReferenceSet(id, TG_UserGroup.user_id, TG_UserGroup.group_id, )

    # collection of all permissions for this group
    #permissions = RelatedJoin("TG_Permission", joinColumn="group_id",
    #    intermediateTable="tg_group_permission",
    #    otherColumn="permission_id")

    @classmethod
    def by_group_name(cls, group_name):
        return store.find(cls, cls.group_name == group_name).one()

class TG_User(object):
    """Reasonably basic User definition."""
    __storm_table__ =  "tg_user"

    id = Int(primary=True)
    user_name = Unicode()
    email_address = Unicode()
    display_name = Unicode()
    created = DateTime(default=datetime.now)

    # groups this user belongs to
    #groups = RelatedJoin("TG_Group", intermediateTable="tg_user_group",
    #    joinColumn="user_id", otherColumn="group_id")
    groups = ReferenceSet(id, TG_UserGroup.user_id, TG_UserGroup.group_id, TG_Group.id)

    @staticmethod
    def _set_password(object, attr_name, new_value):
        """Run cleartext_password through the hash algorithm before saving."""
        try:
            hash = identity.current_provider.encrypt_password(new_value)
        except identity.exceptions.IdentityManagementNotEnabledException:
            # Creating identity provider just to encrypt password
            # (so we don't reimplement the encryption step).
            ip = StormIdentityProvider()
            hash = ip.encrypt_password(new_value)
            if hash == new_value:
                log.info("Identity provider not enabled,"
                    " and no encryption algorithm specified in config."
                    " Setting password as plaintext.")
        return hash

    password = Unicode(validator=_set_password)

    def set_password_raw(self, password):
        """Save the password as-is to the database."""
        self._SO_set_password(password)

    @classmethod
    def by_user_name(cls, user_name):
        return store.find(cls, cls.user_name == user_name).one()

    @classmethod
    def by_email_address(cls, email_address):
        return store.find(cls, cls.email_address == email_address).one()

def encrypt_password(cleartext_password):
    """Encrypt given cleartext password.

    The returned hash consists of the hash of the concatenation of the cleartext password and the salt
    which we then append the salt so we can extract the salt later when we need it for validating the
    password.
    """
    try:
        salt = identity.current_provider.encrypt_password(os.urandom(60))
        hash = identity.current_provider.encrypt_password(cleartext_password + salt) + salt
    except identity.exceptions.RequestRequiredException:
        # Creating identity provider just to encrypt password
        # (so we don't reimplement the encryption step).
        ip = StormIdentityProvider()
        hash = ip.encrypt_password(cleartext_password)
        if hash == cleartext_password:
            log.info("Identity provider not enabled, and no encryption "
                "algorithm specified in config. Setting password as plaintext.")
    return hash

class TG_Permission(object):
    """Permissions for a given group."""
    __storm_table__ = "tg_permission"

    id = Int(primary=True)
    permission_name = Unicode()
    description = Unicode()

    #groups = RelatedJoin("TG_Group", intermediateTable="tg_group_permission",
    #    joinColumn="permission_id", otherColumn="group_id")

    @classmethod
    def by_permission_name(cls, permission_name):
        pass
        