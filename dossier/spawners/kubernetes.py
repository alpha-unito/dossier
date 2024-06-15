from __future__ import annotations

from typing import Any, MutableMapping

from jinja2 import BaseLoader, Environment
from jupyterhub.utils import maybe_future, url_path_join
from kubespawner import KubeSpawner
from kubespawner.clients import shared_client
from tornado.web import Finish
from traitlets.traitlets import Unicode

from dossier import utils


def _get_resource_amount(value, unit):
    if unit == "element":
        return _get_resource_amount_in_elements(value)
    elif unit == "byte":
        return _get_resource_amount_in_bytes(value)
    else:
        raise Exception(f"Unknown resource unit {unit}.")


def _get_resource_amount_in_elements(value):
    if value:
        v = str(value)
        if v.endswith("m"):
            return float(int(v[:-1]) / 1000)
        else:
            return int(v)
    else:
        return 0


def _get_resource_amount_in_bytes(value):
    if value:
        v = str(value)
        if v.endswith("m"):
            return int(v[:-1]) / 1000
        else:
            base = 10
            exponent = 3
            if v.endswith("i"):
                base = 2
                exponent = 10
                v = v[:-1]
            if v.endswith("k"):
                multiplier = base**exponent
                v = v[:-1]
            elif v.endswith("M"):
                multiplier = base ** (2 * exponent)
                v = v[:-1]
            elif v.endswith("G"):
                multiplier = base ** (3 * exponent)
                v = v[:-1]
            elif v.endswith("T"):
                multiplier = base ** (4 * exponent)
                v = v[:-1]
            elif v.endswith("P"):
                multiplier = base ** (5 * exponent)
                v = v[:-1]
            elif v.endswith("E"):
                multiplier = base ** (6 * exponent)
                v = v[:-1]
            else:
                multiplier = 1
            return int(v) * multiplier
    else:
        return 0


class DossierKubeSpawner(KubeSpawner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custom_api = shared_client("CustomObjectsApi")
        self.spawner = None
        self.tenant: MutableMapping[str, Any] | None = None

    default_image_policy = Unicode(
        "fixed",
        config=True,
        help="""
        Image policy to be used to allow users select the Notebook image.

        Supported values are:
          - `fixed` -> only the base (global) image can be used
          - `profiles` -> users can select between multiple available profiles
          - `manual` -> users can manually specify their desired image
        """,
    )

    default_resource_policy = Unicode(
        "fixed",
        config=True,
        help="""
            Resource policy to be used to allow users select the Notebook resources.

            Supported values are:
              - `fixed` -> default limit ranges are used
              - `profiles` -> users can select between multiple available profiles
              - `manual` -> users can manually specify their desired resources
            """,
    )

    default_tenant = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""
        Tenant to be uses when a user has no assigned tenants.

        If the default tenant is not configured, users without assigned tenants won't be able to start
        their pods in Dossier.

        This `tenant` must already exist in the cluster.
        """,
    )

    dossier_options_form_template = Unicode(
        """
        <style>
        .dossier-options-form-group label div input {
            font-weight: normal;
        }
        </style>

        {% if image_policy == "profiles" %}
            <h2>Image Selection</h2>
            {{profile_options_form | safe}}
        {% elif image_policy == "manual" %}
            <h2>Image Selection</h2>
            <div class='form-group dossier-options-form-group' id='dossier-image'>
                <label for="image-item" class='form-control input-group'>
                    <div class='col-md-12'>
                        Image:
                        <input class="form-control" type="text" id="image-item" name="image" value="{{ default_image }}">
                    </div>
                </label>
            </div>
        {% endif %}

        {% if resource_policy == "manual" %}
            <h2>Resources Selection</h2>
            {% for resource in resources %}
                {% set unit = "mUnits" if resource.unit == "element" else "bytes" %}
                <div class='form-group dossier-options-form-group' id='dossier-resource-{{ resource.name }}'>
                    {% if resource.max %}
                    <label for="resource-item-{{ resource.name }}" class='form-control input-group'>
                        <div class="col-md-12">
                            {{ resource.display_name }} (between {{ resource.min }} and {{ resource.max }} {{ unit }}):
                            <input
                                class="form-control"
                                type="range"
                                id="resource-item-{{ resource.name }}"
                                name="{{ resource.name }}"
                                min="{{ resource.min }}"
                                max="{{ resource.max }}"
                                step="{{ resource.step }}"
                                oninput="this.nextElementSibling.value = this.value"
                                {% if resource.default %}
                                    value="{{ resource.default }}"
                                {% endif %}
                            />
                            <output>
                                {% if resource.default %}
                                {{ resource.default }}
                                {% endif %}
                            </output>
                        </div>
                    </label>
                    {% else %}
                    <label for="resource-item-{{ resource.name }}" class="form-control input-group">
                        <div class='col-md-12'>
                            {{ resource.display_name }} ({{ unit }}):
                            <input
                                class="form-control"
                                type="number"
                                id="resource-item-{{ resource.name }}"
                                name="{{ resource.name }}"
                                min="{{ resource.min }}"
                                {% if resource.default %}
                                    value="{ resource.default }}"
                                {% endif %}
                            />
                        </div>
                    </label>
                    {% endif %}
                </div>
            {% endfor %}
        {% endif %}
        """,
        config=True,
        help="""
            Jinja2 template for constructing spawn form shown to user.

            The contents of `profile_list` are passed in to the template.
            This should be used to construct the contents of a HTML form. When
            posted, this form is expected to have an item with name `profile` and
            the value the index of the profile in `profile_list`.
            """,
    )

    async def _get_options_form(self):
        # If tenant has not been configured yet, skip the options form
        if self.tenant is None:
            return None
        # Retrieve annotations from tenant metadata
        annotations = self.tenant["metadata"]["annotations"]
        image_policy = annotations.get(
            "dossier.unito.it/image-policy", self.default_image_policy
        )
        resource_policy = annotations.get(
            "dossier.unito.it/resource-policy", self.default_resource_policy
        )
        profile_options_form = ""
        if image_policy == "profiles":
            if callable(self.profile_list):
                profile_options_form = self._render_options_form_dynamically(
                    self.profile_list
                )
            else:
                profile_options_form = self._render_options_form(self.profile_list)
        if (
            image_policy == "fixed"
            and resource_policy == "fixed"
            and not profile_options_form
        ):
            return None
        dossier_form_template = Environment(loader=BaseLoader()).from_string(
            self.dossier_options_form_template
        )
        resources = {
            "cpu": {
                "name": "cpu",
                "display_name": "CPU",
                "unit": "element",
                "step": 10,
            },
            "memory": {"name": "memory", "display_name": "Memory", "unit": "byte"},
            "nvidia.com/gpu": {
                "name": "gpu",
                "display_name": "GPU",
                "unit": "element",
                "step": 1,
            },
        }
        for item in self.tenant["spec"].get("limitRanges", {}).get("items", []):
            for limit in item.get("limits", []):
                if limit.get("type") == "Container":
                    for r in resources:
                        if r in limit.get("default", {}):
                            resources[r]["default"] = _get_resource_amount(
                                limit["default"][r], resources[r]["unit"]
                            )
                        if r in limit.get("min", {}):
                            resources[r]["min"] = _get_resource_amount(
                                limit["min"][r], resources[r]["unit"]
                            )
                        if r in limit.get("max", {}):
                            resources[r]["max"] = _get_resource_amount(
                                limit["max"][r], resources[r]["unit"]
                            )
                    break
        else:
            for r in resources:
                resources[r]["min"] = 0
        return dossier_form_template.render(
            image_policy=image_policy,
            profile_options_form=profile_options_form,
            default_image=self.image,
            resource_policy=resource_policy,
            resources=list(resources.values()),
        )

    async def _start(self):
        prefix = self.tenant["metadata"]["name"]
        if not self.namespace.startswith(f"{prefix}-"):
            self.namespace = f"{prefix}-{self.namespace}"
        return await maybe_future(super()._start())

    async def get_options_form(self):
        if self.spawner is None:
            spawners = {
                t["metadata"]["name"]: t
                for t in await utils.get_spawners(self.custom_api)
            }
            if len(spawners) == 0:
                self.spawner = self
                return await self._get_options_form()
            else:
                url = url_path_join(
                    self.hub.base_url, "spawner", self.user.escaped_name
                )
                self.handler.redirect(url)
                raise Finish()
        elif self.spawner == self:
            return await self._get_options_form()
        else:
            return await self.spawner.get_options_form()

    async def options_from_form(self, formdata):
        annotations = self.tenant["metadata"]["annotations"]
        image_policy = annotations.get(
            "dossier.unito.it/image-policy", self.default_image_policy
        )
        if image_policy == "profiles":
            profile = formdata.get("profile", [None])[0]
        elif image_policy == "manual":
            profile = formdata.get(
                "profile",
                {
                    "kubespawner_override": {
                        "image": formdata.get("image")[0] or self.image
                    }
                },
            )
        else:
            profile = {"kubespawner_override": {"image": self.image}}
        resource_policy = annotations.get(
            "dossier.unito.it/resource-policy", self.default_resource_policy
        )
        if resource_policy == "profiles":
            pass  # TODO: implement
        elif resource_policy == "manual":
            profile["kubespawner_override"].update(
                {
                    "cpu_limit": int(formdata.get("cpu")[0]) or self.cpu_limit,
                    "cpu_guarantee": int(formdata.get("cpu")[0]) or self.cpu_guarantee,
                    "mem_limit": int(formdata.get("mem")[0]) or self.mem_limit,
                    "mem_guarantee": int(formdata.get("mem")[0]) or self.mem_guarantee,
                }
            )
        else:
            for item in self.tenant["spec"].get("limitRanges", {}).get("items", []):
                for limit in item.get("limits", []):
                    if limit.get("type") == "Container":
                        profile["kubespawner_override"].update(
                            {
                                "cpu_limit": _get_resource_amount(
                                    limit.get("default", {}).get("cpu", self.cpu_limit),
                                    "element",
                                ),
                                "cpu_guarantee": _get_resource_amount(
                                    limit.get("defaultRequest", {}).get(
                                        "cpu", self.cpu_limit
                                    ),
                                    "element",
                                ),
                                "mem_limit": _get_resource_amount(
                                    limit.get("default", {}).get(
                                        "memory", self.mem_limit
                                    ),
                                    "byte",
                                ),
                                "mem_guarantee": _get_resource_amount(
                                    limit.get("defaultRequest", {}).get(
                                        "memory", self.mem_guarantee
                                    ),
                                    "byte",
                                ),
                            }
                        )
                        break
        self.log.debug("Launching profile " + str(profile))
        return {"profile": profile}
