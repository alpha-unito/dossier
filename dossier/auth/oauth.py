from oauthenticator.generic import GenericOAuthenticator


class DossierOAuthenticator(GenericOAuthenticator):

    async def get_authenticated_user(self, handler, data):
        authentication = await super().get_authenticated_user(handler, data)
        tenants = authentication['auth_state']['oauth_user'][self.claim_groups_key]
        authentication['auth_state']['tenants'] = tenants
        return authentication
