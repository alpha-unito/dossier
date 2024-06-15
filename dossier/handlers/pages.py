import importlib
import logging
from typing import Any

from jupyterhub.handlers import BaseHandler
from jupyterhub.handlers.pages import SpawnHandler
from jupyterhub.utils import maybe_future, url_path_join
from kubernetes_asyncio.client import CustomObjectsApi
from kubespawner.clients import load_config, shared_client
from slugify import slugify
from tornado import httputil, web
from tornado.httputil import url_concat
from tornado.web import Application

from dossier import utils
from dossier.spawners.kubernetes import DossierKubeSpawner


class DossierSpawnHandler(SpawnHandler):

    def __init__(
        self,
        application: Application,
        request: httputil.HTTPServerRequest,
        **kwargs: Any,
    ):
        super().__init__(application, request, **kwargs)
        load_config()
        self.api: CustomObjectsApi = shared_client("CustomObjectsApi")

    async def _wrap_spawn_single_user(
        self, user, server_name, spawner, pending_url, options=None
    ):
        if isinstance(spawner, DossierKubeSpawner) and spawner.tenant is None:
            tenants = {
                t["metadata"]["name"]: t for t in await utils.get_tenants(self.api)
            }
            user_groups = {g.name for g in user.orm_user.groups}
            user_tenants = {t for t in tenants if t in user_groups}
            if len(user_tenants) == 0:
                if spawner.default_tenant:
                    if self.log.isEnabledFor(logging.DEBUG):
                        self.log.debug(
                            f"User '{user.escaped_name}' has no tenants assigned. "
                            f"Checking default tenant {spawner.default_tenant}."
                        )
                    if spawner.default_tenant in tenants:
                        spawner.tenant = tenants[spawner.default_tenant]
                        spawner_options_form = await spawner.get_options_form()
                        if spawner_options_form:
                            self.log.debug(
                                "Serving options form for %s", spawner._log_name
                            )
                            form = await self._render_form(
                                for_user=user,
                                spawner_options_form=spawner_options_form,
                            )
                            await maybe_future(self.finish(form))
                        else:
                            self.log.debug(
                                "Triggering spawn with default options for %s",
                                spawner._log_name,
                            )
                            return await super()._wrap_spawn_single_user(
                                user, server_name, spawner, pending_url
                            )
                raise web.HTTPError(
                    403,
                    f"User {user.name} has no tenants assigned and "
                    "no default tenant is defined.",
                )
            elif len(user_tenants) == 1:
                spawner.tenant = tenants[next(iter(user_tenants))]
                if self.log.isEnabledFor(logging.DEBUG):
                    self.log.debug(
                        f"User {user.name} has a single existing "
                        f"tenant assigned: {spawner.tenant}."
                    )
            else:
                url = url_path_join(self.hub.base_url, "tenant", user.escaped_name)
                self.redirect(url)
                return
        else:
            return await super()._wrap_spawn_single_user(
                user, server_name, spawner, pending_url
            )


class DossierSpawnerHandler(BaseHandler):
    def __init__(
        self,
        application: Application,
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
        if user.spawner is None:
            raise web.HTTPError(
                500,
                f"User spawner is None, but it should be a "
                "DossierKubeSpawner instance.",
            )
        if not isinstance(user.spawner, DossierKubeSpawner):
            raise web.HTTPError(
                500,
                f"Invalid spawner class {user.spawner.__class__.__name__}. "
                "User spawner should be a DossierKubeSpawner instance.",
            )
        spawners = {
            t["metadata"]["name"]: t
            for t in await utils.get_spawners(self.api)
            if user.spawner.tenant in t["tenants"]
        }
        spawner_form_objs = [
            {
                "name": "Dossier Spawner",
                "slug": "default",
                "description": "Spawns a Notebook on the selected "
                               f"'{user.spawner.tenant}' Kubernetes Tenant.",
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
            url=url_concat(url, {"_xsrf": self.xsrf_token.decode("ascii")}),
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
            kwargs = {**default_args, **s["spec"]["attributes"]}
            spawner.spawner = class_(**kwargs)
            next_url = self.get_next_url(
                user, default=url_path_join(self.hub.base_url, "spawn")
            )
            self.redirect(next_url)
        else:
            raise web.HTTPError(404, f"Spawner {spawner_name} is not defined.")


class DossierTenantHandler(BaseHandler):
    def __init__(
        self,
        application: Application,
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
        user_groups = {g.name for g in user.orm_user.groups}
        user_tenants = {k: v for k, v in tenants.items() if k in user_groups}
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
            url=url_concat(
                self.request.uri, {"_xsrf": self.xsrf_token.decode("ascii")}
            ),
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
        if tenant in (g.name for g in user.orm_user.groups):
            if t := await utils.get_tenant(self.api, tenant):
                if self.log.isEnabledFor(logging.DEBUG):
                    self.log.debug(
                        f"User {user_name} chose to spawn a Notebook on tenant {tenant}"
                    )
                spawner.tenant = t
                next_url = self.get_next_url(
                    user, default=url_path_join(self.hub.base_url, "spawn")
                )
                self.redirect(next_url)
            else:
                raise web.HTTPError(404, f"Tenant {tenant} is not defined.")
        else:
            raise web.HTTPError(
                403, f"User {user.name} is not assigned to tenant {tenant}."
            )


default_handlers = [
    (r"/spawn", DossierSpawnHandler),
    (r"/spawn/([^/]+)", DossierSpawnHandler),
    (r"/spawn/([^/]+)/([^/]+)", DossierSpawnHandler),
    (r"/spawner", DossierSpawnerHandler),
    (r"/spawner/([^/]+)", DossierSpawnerHandler),
    (r"/tenant", DossierTenantHandler),
    (r"/tenant/(.*)", DossierTenantHandler),
]
