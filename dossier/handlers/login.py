from jupyterhub.handlers import LogoutHandler
from jupyterhub.utils import maybe_future


class DossierLogoutHandler(LogoutHandler):
    async def handle_logout(self):
        user = self.current_user
        if user:
            for spawner in user.spawners.values():
                if self.shutdown_on_logout:
                    if hasattr(spawner, "tenant"):
                        spawner.tenant = None
                    if hasattr(spawner, "confirmed"):
                        delattr(spawner, "confirmed")
                elif not (spawner.ready or spawner.active or spawner.pending):
                    if hasattr(spawner, "tenant"):
                        spawner.tenant = None
                    if hasattr(spawner, "confirmed"):
                        delattr(spawner, "confirmed")
            if hasattr(user, "original_spawner"):
                user.spawners[""] = user.original_spawner
        return await maybe_future(super().handle_logout())


default_handlers = [(r"/logout", DossierLogoutHandler)]
