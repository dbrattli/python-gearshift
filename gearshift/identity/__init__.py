"""The TurboGears identity management package.

@TODO: Laundry list of things yet to be done:
    * IdentityFilter should support HTTP Digest Auth
    * Also want to support Atom authentication (similar to digest)

"""

# declare what should be exported
__all__ = [
    'All',
    'Any',
    'CompoundPredicate',
    'IdentityConfigurationException',
    'IdentityException',
    'IdentityFailure',
    'IdentityManagementNotEnabledException',
    'IdentityPredicateHelper',
    'Predicate',
    'RequestRequiredException',
    'SecureObject',
    'SecureResource',
    'current',
    'current_provider',
    'create_default_provider',
    'encrypt_password',
    'from_host',
    'from_any_host',
    'get_identity_errors',
    'get_failure_url',
    'in_all_groups',
    'in_any_group',
    'in_group',
    'has_all_permissions',
    'has_any_permission',
    'has_permission',
    'not_anonymous',
    'require',
    'set_current_identity',
    'set_current_provider',
    'set_identity_errors',
    'was_login_attempted',
]

from gearshift.identity.base import *
from gearshift.identity.conditions import *
from gearshift.identity.exceptions import *
