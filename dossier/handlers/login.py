from jupyterhub.handlers import LogoutHandler
from jupyterhub.utils import maybe_future

from dossier.spawners.kubernetes import DossierKubeSpawner


class DossierLogoutHandler(LogoutHandler):
    async def handle_logout(self):
        if user := self.current_user:
            for spawner in user.spawners.values():
                if isinstance(spawner, DossierKubeSpawner):
                    if self.shutdown_on_logout or not (
                        spawner.ready or spawner.active or spawner.pending
                    ):
                        spawner.tenant = None
        return await maybe_future(super().handle_logout())


default_handlers = [(r"/logout", DossierLogoutHandler)]
