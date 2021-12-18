from jupyterhub.handlers import LogoutHandler


class DossierLogoutHandler(LogoutHandler):

    def clear_tenants(self):
        user = self.current_user
        for spawner in user.spawners.values():
            if self.shutdown_on_logout:
                spawner.tenant = None
            elif not (spawner.ready or spawner.active or spawner.pending):
                spawner.tenant = None

    async def get(self):
        self.clear_tenants()
        await super().get()


default_handlers = [
    (r'/logout', DossierLogoutHandler)
]
