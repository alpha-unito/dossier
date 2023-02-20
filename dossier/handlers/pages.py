import importlib
from typing import Any

from jupyterhub.handlers import BaseHandler
from jupyterhub.utils import maybe_future, url_path_join
from kubespawner.clients import load_config, shared_client
from slugify import slugify
from tornado import httputil, web

from dossier import utils


class DossierSpawnerHandler(BaseHandler):
    def __init__(
        self,
        application: "Application",
        request: httputil.HTTPServerRequest,
        **kwargs: Any,
    ):
        super().__init__(application, request, **kwargs)
        load_config()
        self.api = shared_client("CustomObjectsApi")

    @web.authenticated
    async def get(self, user_name=None, server_name=""):
        user = current_user = self.current_user
        if user_name is None:
            user_name = current_user.name
        if user_name != user.name:
            user = self.find_user(user_name)
            if user is None:
                raise web.HTTPError(404, f"No such user: {user_name}")
        spawners = {
            t["metadata"]["name"]: t for t in await utils.get_spawners(self.api)
        }
        spawner_form_objs = [
            {
                "name": "Dossier Spawner",
                "slug": "default",
                "description": "Spawns a Notebook on your Kubernetes Tenant",
            }
        ]
        for name in spawners:
            annotations = spawners[name]["metadata"]["annotations"]
            spawner_form_obj = {
                "name": annotations.get("dossier.unito.it/display-name", name)
            }
            if "dossier.unito.it/description" in annotations:
                spawner_form_obj["description"] = annotations[
                    "dossier.unito.it/description"
                ]
            spawner_form_obj["slug"] = slugify(name)
            spawner_form_objs.append(spawner_form_obj)
        url = url_path_join(self.hub.base_url, "spawner", user.escaped_name)
        html = await self.render_template(
            "spawners.html",
            url=url,
            spawners=spawners,
        )
        return self.finish(html)

    @web.authenticated
    async def post(self, user_name=None, server_name=""):
        user = current_user = self.current_user
        if user_name is None:
            user_name = current_user.name
        if user_name != user.name:
            user = self.find_user(user_name)
            if user is None:
                raise web.HTTPError(404, f"No such user: {user_name}")
        spawner = user.spawners[server_name]
        form_options = {}
        for key, byte_list in self.request.body_arguments.items():
            form_options[key] = [bs.decode("utf8") for bs in byte_list]
        spawner_name = form_options.get("spawner")[0]
        if spawner_name == "default":
            spawner.spawner = spawner
            next_url = self.get_next_url(
                user, default=url_path_join(self.hub.base_url, "spawn")
            )
            self.redirect(next_url)
        elif s := await utils.get_spawner(self.api, spawner_name):
            module_name, _, class_simplename = s["spec"]["class"].rpartition(".")
            module = importlib.import_module(module_name)
            class_ = getattr(module, class_simplename)
            default_args = {
                "cmd": spawner.cmd,
                "args": spawner.args,
                "env": spawner.env,
                "user": spawner.user,
                "db": spawner.db,
                "hub": spawner.hub,
                "authenticator": spawner.authenticator,
                "oauth_client_id": spawner.oauth_client_id,
                "orm_spawner": spawner.orm_spawner,
                "proxy_spec": spawner.proxy_spec,
                "server": spawner._server,
                "config": spawner.config,
            }
            kwargs = {**default_args, **s["spec"]["parameters"]}
            spawner.spawner = class_(**kwargs)
            next_url = self.get_next_url(
                user, default=url_path_join(self.hub.base_url, "spawn")
            )
            self.redirect(next_url)
        else:
            raise web.HTTPError(404, "Spawner {} is not defined.", spawner_name, self)


class DossierTenantHandler(BaseHandler):
    def __init__(
        self,
        application: "Application",
        request: httputil.HTTPServerRequest,
        **kwargs: Any,
    ):
        super().__init__(application, request, **kwargs)
        load_config()
        self.api = shared_client("CustomObjectsApi")

    @web.authenticated
    async def get(self, user_name=None, server_name=""):
        user = current_user = self.current_user
        if user_name is None:
            user_name = current_user.name
        if user_name != user.name:
            user = self.find_user(user_name)
            if user is None:
                raise web.HTTPError(404, f"No such user: {user_name}")
        tenants = {t["metadata"]["name"]: t for t in await utils.get_tenants(self.api)}
        user_tenants = {
            k: v
            for k, v in tenants.items()
            if k in (await user.get_auth_state()).get("tenants", [])
        }
        tenant_form_objs = []
        for name, tenant in user_tenants.items():
            annotations = tenant["metadata"]["annotations"]
            tenant_form_obj = {
                "name": annotations.get("dossier.unito.it/display-name", name)
            }
            if "dossier.unito.it/description" in annotations:
                tenant_form_obj["description"] = annotations[
                    "dossier.unito.it/description"
                ]
            tenant_form_obj["slug"] = slugify(name)
            tenant_form_objs.append(tenant_form_obj)
        html = await self.render_template(
            "tenants.html",
            url=self.request.uri,
            tenants=tenant_form_objs,
        )
        await maybe_future(self.finish(html))

    @web.authenticated
    async def post(self, user_name=None, server_name=""):
        user = current_user = self.current_user
        if user_name is None:
            user_name = current_user.name
        if user_name != user.name:
            user = self.find_user(user_name)
            if user is None:
                raise web.HTTPError(404, f"No such user: {user_name}")
        spawner = user.spawners[server_name]
        form_options = {}
        for key, byte_list in self.request.body_arguments.items():
            form_options[key] = [bs.decode("utf8") for bs in byte_list]
        tenant = form_options.get("tenant")[0]
        auth_state = await user.get_auth_state()
        if tenant in auth_state["tenants"]:
            if t := await utils.get_tenant(self.api, tenant):
                spawner.tenant = t
                next_url = self.get_next_url(
                    user, default=url_path_join(self.hub.base_url, "spawn")
                )
                self.redirect(next_url)
            else:
                raise web.HTTPError(404, "Tenant {} is not defined.", tenant, self)
        else:
            raise web.HTTPError(
                403, "User {} is not assigned to tenant {}.", user.name, tenant, self
            )


default_handlers = [
    (r"/spawner", DossierSpawnerHandler),
    (r"/spawner/([^/]+)", DossierSpawnerHandler),
    (r"/tenant", DossierTenantHandler),
    (r"/tenant/(.*)", DossierTenantHandler),
]
