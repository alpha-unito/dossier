from jupyterhub.handlers import LogoutHandler


class DossierLogoutHandler(LogoutHandler):

    def clear_tenants(self):
        user = self.current_user
        for spawner in user.spawners.values():
            if self.shutdown_on_logout:
                if hasattr(spawner, 'tenant'):
                    spawner.tenant = None
                if hasattr(spawner, 'confirmed'):
                    delattr(spawner, 'confirmed')
            elif not (spawner.ready or spawner.active or spawner.pending):
                if hasattr(spawner, 'tenant'):
                    spawner.tenant = None
                if hasattr(spawner, 'confirmed'):
                    delattr(spawner, 'confirmed')
        if hasattr(user, 'original_spawner'):
            user.spawners[''] = user.original_spawner

    async def get(self):
        self.clear_tenants()
        await super().get()


default_handlers = [
    (r'/logout', DossierLogoutHandler)
]
