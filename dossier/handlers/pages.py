from jupyterhub.handlers import BaseHandler
from jupyterhub.handlers.pages import SpawnHandler
from jupyterhub.utils import url_path_join, maybe_future
from tornado import web


def _check_impersonate(handler, user, for_user):
    if for_user is not None and for_user != user.name:
        if not user.admin:
            raise web.HTTPError(
                403, "Only admins can spawn on behalf of other users"
            )
        user = handler.find_user(for_user)
        if user is None:
            raise web.HTTPError(404, "No such user: %s" % for_user)
    return user


class DossierSpawnHandler(SpawnHandler):

    @web.authenticated
    async def get(self, for_user=None, server_name=''):
        user = _check_impersonate(self, self.current_user, for_user)
        auth_state = await user.get_auth_state()
        spawner = user.spawners[server_name]
        if spawner.tenant is None:
            tenants = {t['metadata']['name']: t
                       for t in spawner.get_tenants() if t['metadata']['name'] in auth_state['tenants']}
            if len(tenants) == 0:
                if spawner.default_tenant_name:
                    if spawner.default_tenant_name in tenants:
                        spawner.tenant = tenants[spawner.default_tenant_name]
                    else:
                        raise web.HTTPError(
                            404,
                            "Tenant {} is not defined.", spawner.default_tenant_name, self)
                else:
                    raise web.HTTPError(
                        403,
                        "User {} has no tenants assigned.", user.name, self)
            elif len(tenants) == 1:
                spawner.tenant = list(tenants.values())[0]
                await super().get(for_user=for_user, server_name=server_name)
            else:
                url = url_path_join(self.hub.base_url, 'tenant', user.escaped_name)
                html = await self.render_template(
                    'dossier/tenants.html',
                    no_spawner_check=True,
                    url=url,
                    dossier_spawner_tenants_form=spawner.render_tenants_form(tenants))
                self.finish(html)
        else:
            await super().get(for_user=for_user, server_name=server_name)


class DossierTenantHandler(BaseHandler):

    @web.authenticated
    async def post(self, for_user=None, server_name=''):
        user = _check_impersonate(self, self.current_user, for_user)
        spawner = user.spawners[server_name]
        form_options = {}
        for key, byte_list in self.request.body_arguments.items():
            form_options[key] = [bs.decode('utf8') for bs in byte_list]
        for key, byte_list in self.request.files.items():
            form_options["%s_file" % key] = byte_list
        options = await maybe_future(spawner.tenant_from_form(form_options))
        tenant = options['tenant']
        auth_state = await user.get_auth_state()
        if tenant in auth_state['tenants']:
            if t := spawner.get_tenant(tenant):
                spawner.tenant = t
                next_url = self.get_next_url(user, default=url_path_join(self.hub.base_url, 'spawn'))
                self.redirect(next_url)
            else:
                raise web.HTTPError(
                    404,
                    "Tenant {} is not defined.", tenant, self)
        else:
            raise web.HTTPError(
                403,
                "User {} is not assigned to tenant {}.", user.name, tenant, self)


default_handlers = [
    (r'/spawn', DossierSpawnHandler),
    (r'/spawn/([^/]+)', DossierSpawnHandler),
    (r'/spawn/([^/]+)/([^/]+)', DossierSpawnHandler),
    (r'/tenant', DossierTenantHandler),
    (r'/tenant/([^/]+)', DossierTenantHandler),
]
