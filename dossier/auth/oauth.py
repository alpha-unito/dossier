import logging

from kubernetes_asyncio.client import CustomObjectsApi
from kubespawner.clients import load_config, shared_client
from oauthenticator.generic import GenericOAuthenticator

from dossier import utils


class DossierOAuthenticator(GenericOAuthenticator):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        load_config()
        self.api: CustomObjectsApi = shared_client("CustomObjectsApi")

    async def check_allowed(self, username, authentication=None):
        if await super().check_allowed(username, authentication):
            return True
        if self.manage_groups:
            if self.log.isEnabledFor(logging.DEBUG):
                self.log.debug(
                    f"User {username} belongs to the following groups: {authentication['groups']}."
                )
            # Users that belong to an existing tenant are allowed
            tenants = {t["metadata"]["name"] for t in await utils.get_tenants(self.api)}
            if self.log.isEnabledFor(logging.DEBUG):
                if tenants:
                    self.log.debug(
                        f"The following tenants have been found on the cluster: {','.join(tenants)}."
                    )
                else:
                    self.log.debug("No tenants found on the cluster.")
            return any(set(authentication["groups"]) & tenants)
        else:
            if self.log.isEnabledFor(logging.WARNING):
                self.log.warning(
                    "Tenants support is disabled. Please activate the `manage_groups` option "
                    "for the `Authenticator` class to enable it."
                )
            return False
