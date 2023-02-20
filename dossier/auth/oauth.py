from jupyterhub.utils import maybe_future
from kubespawner.clients import shared_client
from oauthenticator.generic import GenericOAuthenticator

from dossier import utils


class DossierOAuthenticator(GenericOAuthenticator):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api = shared_client("CustomObjectsApi")

    def _get_user_groups(self, authentication=None):
        if authentication is not None:
            return authentication.get("auth_state", {}).get("oauth_user", {}).get(self.claim_groups_key, [])
        else:
            return []

    async def check_allowed(self, username, authentication=None):
        groups = self._get_user_groups()
        if self.check_user_in_groups(groups, self.admin_groups):
            return True
        tenants = [t['metadata']['name'] for t in utils.get_tenants()]
        if self.check_user_in_groups(groups, tenants):
            return True
        return await maybe_future(super().check_allowed(username, authentication))

    def is_admin(self, handler, authentication):
        groups = self._get_user_groups()
        if self.check_user_in_groups(groups, self.admin_groups):
            return True
        else:
            return super().is_admin(handler, authentication)
