# coding=UTF-8
import re
import unittest
import urllib
import formencode
import cherrypy
from gearshift import testutil, database, identity, config, startup, expose
from gearshift.controllers import Controller, RootController
from gearshift.identity import SecureResource, \
    has_permission, in_group, not_anonymous
from gearshift.identity.soprovider import TG_User, TG_Group, TG_Permission

hub = database.AutoConnectHub("sqlite:///:memory:")
#hub = database.PackageHub("gearshift.identity")


def mycustomencrypt(password):
    return password + '_custom'


class RestrictedArea(Controller, SecureResource):

    require = in_group('peon')

    @expose()
    def index(self):
        return "restricted_index"

    @expose()
    @identity.require(in_group('admin'))
    def in_admin_group(self):
        return 'in_admin_group'

    @expose()
    @identity.require(in_group('other'))
    def in_other_group(self):
        return 'in_other_group'

    @expose()
    def in_admin_group_explicit_check(self):
        if 'admin' not in identity.current.groups:
            raise identity.IdentityFailure("You need to be an Admin")
        else:
            return 'in_admin_group'

    @expose()
    def in_other_group_explicit_check(self):
        if 'other' not in identity.current.groups:
            raise identity.IdentityException
        else:
            return 'in_other_group'


class IdentityRoot(RootController):

    _cp_config = {
        'tools.decode.on' : True
    }

    @expose()
    def index(self):
        return dict()

    @expose()
    def identity_failed(self, **kw):
        cherrypy.response.status = 401
        return 'identity_failed_answer'

    @expose()
    @identity.require(not_anonymous())
    def logged_in_only(self):
        return 'logged_in_only'

    @expose()
    @identity.require(in_group('peon'))
    def in_peon_group(self):
        user = TG_User.by_user_name("samIam")
        group_ids = set((TG_Group.by_group_name("peon").id,
            TG_Group.by_group_name("other").id))
        assert identity.current.user == user
        assert identity.current.user_name == user.user_name
        assert identity.current.user_id == user.id
        assert identity.current.groups == set(('peon', 'other'))
        assert identity.current.group_ids == group_ids
        assert "samIam" == cherrypy.serving.request.identity.user_name

        return 'in_peon_group'

    @expose()
    def test_exposed_require(self):
        print self.in_peon_group._cp_config
        if not self.in_peon_group._cp_config.has_key('tools.identity.require'):
            return 'no require config'
        if not isinstance(self.in_peon_group._cp_config['tools.identity.require'], in_group):
            return 'not correct class'
        if 'peon' != self.in_peon_group._cp_config['tools.identity.require'].group_name:
            return 'not correct group name'
        return 'require is exposed'

    @expose()
    @identity.require(in_group('admin'))
    def in_admin_group(self):
        return 'in_admin_group'

    @expose()
    @identity.require(has_permission('chops_wood'))
    def has_chopper_permission(self):
        return 'has_chopper_permission'

    @expose()
    @identity.require(has_permission('bosses_people'))
    def has_boss_permission(self):
        return "has_boss_permission"

    @expose()
    def logout(self):
        identity.current.logout()
        return "logged out"

    @expose()
    @identity.require(not_anonymous())
    def user_email(self):
        return identity.current.user.email_address

    peon_area = RestrictedArea()

    @expose()
    def new_user_setup(self, user_name, password):
        return '%s %s' % (user_name, password)

    _test_encoded_params = ('b=krümel&d.a=klöße1')

    @expose()
    @identity.require(not_anonymous())
    def test_params(self, **kwargs):
        params = self._test_encoded_params
        # formencode's variable_decode create a datastructure
        #  but does not "decode" anything
        to_datastruct = formencode.variabledecode.variable_decode
        expected_params = to_datastruct(
            dict([p.split('=') for p in params.split('&')]))
        params_ok = True
        print expected_params
        print cherrypy.request.params
        if not expected_params['b'].decode(
                'utf8') == cherrypy.request.params['b']:
            params_ok = False
        if not expected_params['d']['a'].decode(
                'utf8') == cherrypy.request.params['d.a']:
            params_ok = False
        if params_ok:
            return 'params ok'
        else:
            return 'wrong params: %s\nexpected unicode objects' \
                ' for all strings' % cherrypy.request.params

    @expose()
    def is_anonymous(self):
        assert cherrypy.serving.request.identity.user_name == None
        assert cherrypy.serving.request.identity.anonymous
        assert identity.current.anonymous
        return 'is_anonymous'



class TestIdentity(testutil.TGTest):

    def setUp(self):
        # identity requires visit and a failure_url
        test_config = {'global': {
            'tools.visit.on': True, 'tools.identity.on': True,
            'tools.identity.failure_url': '/identity_failed',
            'tools.identity.soprovider.encryption_algorithm': None}}
        original_config = dict()
        for key in test_config['global']:
            original_config[key] = config.get(key)
        self._original_config = original_config
        #config.configure_loggers(test_config)
        config.update(test_config['global'])
        self.root = IdentityRoot
        testutil.TGTest.setUp(self)
        self.init_model()

    def tearDown(self):
        testutil.TGTest.tearDown(self)
        config.update(self._original_config)

    def init_model(self):
        if TG_User.select().count() == 0:
            user = TG_User(user_name='samIam',
                email_address='samiam@example.com',
                display_name='Samuel Amicus', password='secret')
            admin_group = TG_Group(group_name="admin",
                display_name="Administrator")
            peon_group = TG_Group(group_name="peon",
                display_name="Regular Peon")
            other_group = TG_Group(group_name="other",
            display_name="Another Group")
            chopper_perm = TG_Permission(permission_name='chops_wood',
                description="Wood Chopper")
            boss_perm = TG_Permission(permission_name='bosses_people',
                description="Benevolent Dictator")
            peon_group.addTG_Permission(chopper_perm)
            admin_group.addTG_Permission(boss_perm)
            user.addTG_Group(peon_group)
            user.addTG_Group(other_group)

    def test_user_password_parameters(self):
        """Controller can receive user_name and password parameters."""
        response = self.app.get('/new_user_setup?user_name=test&password=pw')
        assert 'test pw' in response

    def test_user_exists(self):
        u = TG_User.by_user_name('samIam')
        assert u.email_address == 'samiam@example.com'

    def test_user_password(self):
        """Test if we can set a user password (no encryption algorithm)."""
        hub.begin()
        u = TG_User.by_user_name('samIam')
        u.password='password'
        u.sync()
        assert u.password == 'password'
        hub.rollback()
        hub.end()

    def test_user_password_unicode(self):
        """Test if we can set a user password which is encoded as unicode
        (no encryption algorithm)."""
        config.update({'tools.identity.soprovider.encryption_algorithm': None})
        # force new config values to load
        startup.startTurboGears()
        self.app.get('/')
        hub.begin()
        u = TG_User.by_user_name('samIam')
        u.password = u'garçon'
        u.sync()
        assert u.password == u'garçon'
        hub.rollback()
        hub.end()

    def test_user_password_hashed_sha(self):
        """Test if a sha hashed password is stored in the database."""
        config.update({'tools.identity.soprovider.encryption_algorithm': 'sha1'})
        # force new config values to load
        startup.startTurboGears()
        self.app.get('/')
        hub.begin()
        u = TG_User.by_user_name('samIam')
        u.password = 'password'
        u.sync()
        assert u.password =='5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8'
        hub.rollback()
        hub.end()

    def test_user_password_hashed_sha_unicode(self):
        """Test if a sha hashed password with unicode characters is stored
        in the database."""
        config.update({'tools.identity.soprovider.encryption_algorithm': 'sha1'})
        # force new config values to load
        startup.startTurboGears()
        self.app.get('/')
        hub.begin()
        u = TG_User.by_user_name('samIam')
        u.password = u'garçon'
        u.sync()
        assert u.password == '442edb21c491a6e6f502eb79e98614f3c7edf43e'
        hub.rollback()
        hub.end()

    def test_user_password_hashed_md5(self):
        """Test if a md5 hashed password is stored in the database."""
        config.update({'tools.identity.soprovider.encryption_algorithm': 'md5'})
        # force new config values to load
        startup.startTurboGears()
        self.app.get('/')
        hub.begin()
        u = TG_User.by_user_name('samIam')
        u.password = 'password'
        u.sync()
        assert u.password =='5f4dcc3b5aa765d61d8327deb882cf99'
        hub.rollback()
        hub.end()

    def test_user_password_hashed_md5_unicode(self):
        """Test if a md5 hashed password with unicode characters is stored
        in the database."""
        config.update({'tools.identity.soprovider.encryption_algorithm': 'md5'})
        # force new config values to load
        startup.startTurboGears()
        self.app.get('/')
        hub.begin()
        u = TG_User.by_user_name('samIam')
        u.password = u'garçon'
        u.sync()
        assert u.password == 'c295c4bb2672ca8c432effc53b40bb1e'
        hub.rollback()
        hub.end()

    def test_user_password_hashed_md5_utf8string(self):
        """Test if a md5 hashed password with unicode characters is stored in
        the database if the password is entered as str (encoded in UTF-8). This
        test ensures that the encryption algorithm does handle non-unicode
        parameters gracefully."""
        config.update({'tools.identity.soprovider.encryption_algorithm': 'md5'})
        # force new config values to load
        startup.startTurboGears()
        self.app.get('/')
        hub.begin()
        u = TG_User.by_user_name('samIam')
        u.password = u'garçon'.encode('UTF-8')
        u.sync()
        assert u.password == 'c295c4bb2672ca8c432effc53b40bb1e'
        hub.rollback()
        hub.end()

    def test_user_password_raw(self):
        """Test that we can store raw values in the password field
        (without being hashed)."""
        config.update({'tools.identity.soprovider.encryption_algorithm':'sha1'})
        # force new config values to load
        startup.startTurboGears()
        self.app.get('/')
        hub.begin()
        u = TG_User.by_user_name('samIam')
        u.set_password_raw('password')
        u.sync()
        assert u.password =='password'
        hub.rollback()
        hub.end()

    def test_user_password_raw_unicode(self):
        config.update({'tools.identity.soprovider.encryption_algorithm':'sha1'})
        # force new config values to load
        startup.startTurboGears()
        self.app.get('/')
        hub.begin()
        u = TG_User.by_user_name('samIam')
        u.set_password_raw(u'garçon')
        u.sync()
        assert u.password == u'garçon'
        hub.rollback()
        hub.end()

    def test_user_password_hashed_custom(self):
        """Test if a custom hashed password is stored in the database."""
        config.update({'tools.identity.soprovider.encryption_algorithm': 'custom',
            'tools.identity.custom_encryption':
                'identity.tests.test_identity.mycustomencrypt'})
        # force new config values to load
        startup.startTurboGears()
        self.app.get('/')
        hub.begin()
        u = TG_User.by_user_name('samIam')
        u.password = 'password'
        u.sync()
        assert u.password =='password_custom'
        hub.rollback()
        hub.end()

    def test_anonymous_browsing(self):
        """Test if we can show up anonymously."""
        response = self.app.get('/is_anonymous')
        assert 'is_anonymous' in response

    def test_deny_anonymous(self):
        """Test that we have secured an url from anonymous users."""
        response = self.app.get('/logged_in_only', status=401)
        assert 'identity_failed_answer' in response

    def test_deny_anonymous_viewable(self):
        """Test that a logged in user can see an resource blocked
        from anonymous users."""
        response = self.app.get('/logged_in_only?'
            'user_name=samIam&password=secret&login=Login')
        assert 'logged_in_only' in response

    def test_logout(self):
        """Test that logout works and session is gets invalid afterwards."""
        response = self.app.get('/in_peon_group?'
            'user_name=samIam&password=secret&login=Login')
        session_id = response.headers['Set-Cookie']
        response = self.app.get('/logout', headers={'Cookie': session_id })
        response = self.app.get('/is_anonymous', headers={'Cookie': session_id})
        assert response.body == 'is_anonymous'

    def test_require_group(self):
        """Test that a anonymous user"""
        response = self.app.get('/in_peon_group', status=401)
        assert 'identity_failed_answer' in response, response

    def test_require_expose_required_permission(self):
        """Test that the decorator exposes the correct permissions via _require
        attribute on the actual method."""
        response = self.app.get('/test_exposed_require')
        assert 'require is exposed' in response, response

    def test_require_group_viewable(self):
        """Test that a user with proper group membership can see a restricted url."""
        response = self.app.get('/in_peon_group?'
            'user_name=samIam&password=secret&login=Login')
        assert 'in_peon_group' in response, response
        user = TG_User.by_user_name("samIam")

    def test_require_group_viewable(self):
        """Test that the current user and group properties are set correctly."""
        response = self.app.get('/in_peon_group?'
            'user_name=samIam&password=secret&login=Login')
        user = TG_User.by_user_name("samIam")
        group_ids = set((TG_Group.by_group_name("peon").id,
            TG_Group.by_group_name("other").id))

    def test_user_not_in_right_group(self):
        """Test that a user is denied access if they aren't in the right group.
        """
        response = self.app.get('/in_admin_group?'
            'user_name=samIam&password=secret&login=Login', status=401)
        assert 'identity_failed_answer' in response, response

    def test_require_permission(self):
        """Test that an anonymous user is denied access to a permission
        restricted url.
        """
        response = self.app.get('/has_chopper_permission', status=401)
        assert 'identity_failed_answer' in response, response

    def test_require_permission_viewable(self):
        """Test that a user with proper permissions can see a restricted url."""
        response = self.app.get('/has_chopper_permission?'
            'user_name=samIam&password=secret&login=Login')
        assert 'has_chopper_permission' in response

    def test_user_lacks_permission(self):
        """Test that a user is denied acces if they don't have the proper
        permission.
        """
        response = self.app.get('/has_boss_permission?'
            'user_name=samIam&password=secret&login=Login', status=401)
        assert 'identity_failed_answer' in response, response

    def test_user_info_available(self):
        """Test that we can see user information inside our controller."""
        response = self.app.get('/user_email?'
            'user_name=samIam&password=secret&login=Login')
        assert 'samiam@example.com' in response, response

    def test_bad_login(self):
        """Test that we are denied access if we provide a bad login."""
        response = self.app.get('/logged_in_only?'
            'user_name=samIam&password=wrong&login=Login', status=401)
        assert 'identity_failed_answer' in response, response

    def test_restricted_subdirectory(self):
        """Test that we can restrict access to a whole subdirectory."""
        response = self.app.get('/peon_area/index', status=401)
        assert 'identity_failed_answer' in response, response

    def test_restricted_subdirectory_viewable(self):
        """Test that we can access a restricted subdirectory
        if we have proper credentials."""
        response = self.app.get('/peon_area/index?'
            'user_name=samIam&password=secret&login=Login')
        assert 'restricted_index' in response, response

    def test_decoratator_in_restricted_subdirectory(self):
        """Test that we can require a different permission
        in a protected subdirectory."""
        response = self.app.get('/peon_area/in_other_group?'
            'user_name=samIam&password=secret&login=Login')
        assert 'in_other_group' in response, response

    def test_decoratator_failure_in_restricted_subdirectory(self):
        """Test that we can get an identity failure from a decorator
        in a restricted subdirectory"""
        response = self.app.get('/peon_area/in_admin_group?'
            'user_name=samIam&password=secret&login=Login', status=401)
        assert 'identity_failed_answer' in response, response

    def test_explicit_checks_in_restricted_subdirectory(self):
        """Test that explicit permission checks in a protected
        directory is handled as expected"""
        response = self.app.get('/peon_area/in_other_group_explicit_check?'
            'user_name=samIam&password=secret&login=Login')
        assert 'in_other_group' in response, response

    def test_throwing_identity_exception_in_restricted_subdirectory(self):
        """Test that throwing an IdentityException in a protected
        directory is handled as expected"""
        response = self.app.get('/peon_area/in_admin_group_explicit_check?'
            'user_name=samIam&password=secret&login=Login', status=401)
        assert 'identity_failed' in response, response

    def test_decode_filter_whenidfails(self):
        """Test that the decode filter doesn't break with nested
        variables and Identity"""
        params = urllib.quote(IdentityRoot._test_encoded_params.decode(
            'utf-8').encode('latin-1'), '=&')
        response = self.app.get('/test_params?' + params, status=401)
        assert 'identity_failed_answer' in response, response

    def test_decode_filter_whenidworks(self):
        """Test that the decode filter doesn't break with nested
        variables and Identity"""
        params = urllib.quote(IdentityRoot._test_encoded_params.decode(
            'utf-8').encode('latin-1'), '=&')
        params += '&user_name=samIam&password=secret&login=Login'
        response = self.app.get('/test_params?' + params)
        assert 'params ok' in response, response


class TestTGUser(testutil.DBTest):
    model = TG_User

    def setUp(self):
        self._identity_on = config.get('tools.identity.on', False)
        config.update({'tools.identity.on': False})
        startup.startTurboGears()
        testutil.DBTest.setUp(self)

    def tearDown(self):
        testutil.DBTest.tearDown(self)
        startup.stopTurboGears()
        config.update({'tools.identity.on': self._identity_on})

    def test_create_user(self):
        """Check that User can be created outside of a running identity provider."""
        u = TG_User(user_name='testcase',
            email_address='testcase@example.com',
            display_name='Test Me', password='test')
        assert u.password=='test', u.password
