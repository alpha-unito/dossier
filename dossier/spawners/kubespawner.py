import asyncio
import uuid
from typing import MutableMapping

from jinja2 import BaseLoader, Environment
from kubernetes_asyncio.client import ApiException
from kubespawner import KubeSpawner
from kubespawner.clients import shared_client
from kubespawner.objects import make_namespace
from slugify import slugify
from tornado import gen
from traitlets import Unicode


def _get_resource_amount(value, unit):
    if unit == 'element':
        return _get_resource_amount_in_elements(value)
    elif unit == 'byte':
        return _get_resource_amount_in_bytes(value)
    else:
        raise Exception("Unknown resource unit {}.".format(unit))


def _get_resource_amount_in_elements(value):
    if value:
        v = str(value)
        if v.endswith('m'):
            return float(int(v[:-1]) / 1000)
        else:
            return int(v)
    else:
        return 0


def _get_resource_amount_in_bytes(value):
    if value:
        v = str(value)
        if v.endswith('m'):
            return int(v[:-1]) / 1000
        else:
            base = 10
            exponent = 3
            if v.endswith('i'):
                base = 2
                exponent = 10
                v = v[:-1]
            if v.endswith('k'):
                multiplier = base ** exponent
                v = v[:-1]
            elif v.endswith('M'):
                multiplier = base ** (2 * exponent)
                v = v[:-1]
            elif v.endswith('G'):
                multiplier = base ** (3 * exponent)
                v = v[:-1]
            elif v.endswith('T'):
                multiplier = base ** (4 * exponent)
                v = v[:-1]
            elif v.endswith('P'):
                multiplier = base ** (5 * exponent)
                v = v[:-1]
            elif v.endswith('E'):
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
        self.custom_api = shared_client('CustomObjectsApi')
        self.tenant = None

    default_image_policy = Unicode(
        "fixed",
        config=True,
        help="""
        Image policy to be used to allow users select the Notebook image.
        
        Supported values are:
          - `fixed` -> only the base (global) image can be used
          - `profiles` -> users can select between multiple available profiles
          - `manual` -> users can manually specify their desired image
        """
    )

    default_resource_policy = Unicode(
        "fixed",
        config=True,
        help="""
            Resource policy to be used to allow users select the Notebook resourcs.

            Supported values are:
              - `fixed` -> default limit ranges are used
              - `profiles` -> users can select between multiple available profiles
              - `manual` -> users can manually specify their desired resources
            """
    )

    default_tenant_name = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""
        Tenant to be uses when a user has no assigned tenants.
        
        If the default tenant is not configured, users without assigned tenants won't be able to start
        their pods in Dossier.
        
        This `tenant` must already exist in the cluster. 
        """
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

    dossier_spawners_form_template = Unicode(
        """
        <style>
            #dossier-spawners-list label span {
                font-weight: normal;
            }
            .vcenter {
                display: inline-block;
                float: none;
                vertical-align: middle;
            }
        </style>
        <div class='form-group' id='dossier-spawners-list'>
        {% for spawner in spawners %}
            <label for='spawner-item-{{ spawner.name }}' class='form-control input-group'>
                <div class='col-md-1 vcenter'>
                    <input
                        type='radio'
                        name='spawner'
                        id='spawner-item-{{ spawner.slug }}'
                        value='{{ spawner.slug }}' />
                </div>
                <div class='col-md-10 vcenter'>
                    <strong>{{ spawner.name }}</strong>
                    {% if spawner.description %}
                        <span> - {{ spawner.description }}</span>
                    {% endif %}
                </div>
            </label>
        {% endfor %}
        </div>
        """,
        config=True,
        help="""
            Jinja2 template for constructing the spawners form shown to user.

            The contents of the `spawners` variable are passed in to the template.
            This should be used to construct the contents of a HTML form. When
            posted, this form is expected to have an item with name `spawner` and
            the value of the index of the tenant in the `spawners` variable.
        """
    )

    dossier_tenants_form_template = Unicode(
        """
        <style>
            #dossier-tenants-list label span {
                font-weight: normal;
            }
            .vcenter {
                display: inline-block;
                float: none;
                vertical-align: middle;
            }
        </style>
        <div class='form-group' id='dossier-tenants-list'>
        {% for tenant in tenants %}
            <label for='tenant-item-{{ tenant.name }}' class='form-control input-group'>
                <div class='col-md-1 vcenter'>
                    <input
                        type='radio'
                        name='tenant'
                        id='tenant-item-{{ tenant.slug }}'
                        value='{{ tenant.slug }}' />
                </div>
                <div class='col-md-10 vcenter'>
                    <strong>{{ tenant.name }}</strong>
                    {% if tenant.description %}
                        <span> - {{ tenant.description }}</span>
                    {% endif %}
                </div>
            </label>
        {% endfor %}
        </div>
        """,
        config=True,
        help="""
            Jinja2 template for constructing the tenants form shown to user.

            The contents of the `tenants` variable are passed in to the template.
            This should be used to construct the contents of a HTML form. When
            posted, this form is expected to have an item with name `tenant` and
            the value of the index of the tenant in the `tenants` variable.
        """
    )

    async def _ensure_namespace(self):
        ns = make_namespace(
            f"{self.tenant['metadata']['name']}-{self.namespace}",
            labels=self._expand_all(self.user_namespace_labels),
            annotations=self._expand_all(self.user_namespace_annotations),
        )
        api = self.api
        try:
            await asyncio.wait_for(
                api.create_namespace(ns),
                self.k8s_api_request_timeout,
            )
        except ApiException as e:
            if e.status != 409:
                # It's fine if it already exists
                self.log.exception("Failed to create namespace %s", self.namespace)
                raise

    def get_spawner(self, name):
        try:
            return self.custom_api.get_cluster_custom_object(
                group="dossier.unito.it",
                version="v1alpha1",
                plural="spawners",
                name=name)
        except ApiException as error:
            if error.status == 404:
                return None
            else:
                raise error

    def get_spawners(self):
        return self.custom_api.list_cluster_custom_object(
            group="dossier.unito.it",
            version="v1alpha1",
            plural="spawners")['items']

    def get_tenant(self, name):
        try:
            return self.custom_api.get_cluster_custom_object(
                group="capsule.clastix.io",
                version="v1beta1",
                plural="tenants",
                name=name)
        except ApiException as error:
            if error.status == 404:
                return None
            else:
                raise error

    def get_tenants(self):
        return self.custom_api.list_cluster_custom_object(
            group="capsule.clastix.io",
            version="v1beta1",
            plural="tenants")['items']

    async def get_options_form(self):
        annotations = self.tenant['metadata']['annotations']
        image_policy = annotations.get('dossier.unito.it/image-policy', self.default_image_policy)
        resource_policy = annotations.get('dossier.unito.it/resource-policy', self.default_resource_policy)
        profile_options_form = ''
        if image_policy == "profiles":
            if callable(self.profile_list):
                profile_options_form = self._render_options_form_dynamically(self.profile_list)
            else:
                profile_options_form = self._render_options_form(self.profile_list)
        if image_policy == 'fixed' and resource_policy == 'fixed' and not profile_options_form:
            return ''
        dossier_form_template = Environment(loader=BaseLoader()).from_string(
            self.dossier_options_form_template
        )
        resources = {
            'cpu': {'name': 'cpu', 'display_name': 'CPU', 'unit': 'element', 'step': 10},
            'memory': {'name': 'memory', 'display_name': 'Memory', 'unit': 'byte'},
            'nvidia.com/gpu': {'name': 'gpu', 'display_name': 'GPU', 'unit': 'element', 'step': 1}
        }
        for item in self.tenant['spec'].get('limitRanges', {}).get('items', []):
            for limit in item.get('limits', []):
                if limit.get('type') == 'Container':
                    for r in resources:
                        if r in limit.get('default', {}):
                            resources[r]['default'] = _get_resource_amount(
                                limit['default'][r],
                                resources[r]['unit'])
                        if r in limit.get('min', {}):
                            resources[r]['min'] = _get_resource_amount(
                                limit['min'][r],
                                resources[r]['unit'])
                        if r in limit.get('max', {}):
                            resources[r]['max'] = _get_resource_amount(
                                limit['max'][r],
                                resources[r]['unit'])
                    break
        else:
            for r in resources:
                resources[r]['min'] = 0
        return dossier_form_template.render(
            image_policy=image_policy,
            profile_options_form=profile_options_form,
            default_image=self.image,
            resource_policy=resource_policy,
            resources=list(resources.values()))

    async def load_user_options(self):
        if self._profile_list is None:
            if callable(self.profile_list):
                profile_list = await gen.maybe_future(self.profile_list(self))
            else:
                profile_list = self.profile_list

            self._profile_list = self._init_profile_list(profile_list)

        selected_profile = self.user_options.get('profile', None)
        if self._profile_list:
            await self._load_profile(selected_profile)
        elif selected_profile:
            if isinstance(selected_profile, MutableMapping):
                random_name = str(uuid.uuid4())
                selected_profile['display_name'] = "Dynamically generated profile"
                selected_profile['slug'] = random_name
                self._profile_list.append(selected_profile)
                try:
                    await self._load_profile(random_name)
                finally:
                    for profile in list(self._profile_list):
                        if profile['slug'] == random_name:
                            self._profile_list.remove(profile)
                            break
            else:
                self.log.warning("Profile %r requested, but profiles are not enabled", selected_profile)

        # help debugging by logging any option fields that are not recognized
        option_keys = set(self.user_options)
        unrecognized_keys = option_keys.difference(self._user_option_keys)
        if unrecognized_keys:
            self.log.warning(
                "Ignoring unrecognized KubeSpawner user_options: %s",
                ", ".join(map(str, sorted(unrecognized_keys))),
            )

    def render_spawners_form(self, spawners):
        dossier_form_template = Environment(loader=BaseLoader()).from_string(
            self.dossier_spawners_form_template)
        spawner_form_objs = [{
            'name': 'Dossier Spawner',
            'slug': 'default',
            'description': 'Spawns a Notebook on your Kubernetes Tenant'}]
        for name in spawners:
            annotations = spawners[name]['metadata']['annotations']
            spawner_form_obj = {'name': annotations.get('dossier.unito.it/display-name', name)}
            if 'dossier.unito.it/description' in annotations:
                spawner_form_obj['description'] = annotations['dossier.unito.it/description']
            spawner_form_obj['slug'] = slugify(name)
            spawner_form_objs.append(spawner_form_obj)
        return dossier_form_template.render(spawners=spawner_form_objs)

    def render_tenants_form(self, tenants):
        dossier_form_template = Environment(loader=BaseLoader()).from_string(
            self.dossier_tenants_form_template)
        tenant_form_objs = []
        for name in tenants:
            annotations = tenants[name]['metadata']['annotations']
            tenant_form_obj = {'name': annotations.get('dossier.unito.it/display-name', name)}
            if 'dossier.unito.it/description' in annotations:
                tenant_form_obj['description'] = annotations['dossier.unito.it/description']
            tenant_form_obj['slug'] = slugify(name)
            tenant_form_objs.append(tenant_form_obj)
        return dossier_form_template.render(tenants=tenant_form_objs)

    async def spawner_from_form(self, formdata):
        return {'spawner': formdata.get('spawner')[0]}

    async def tenant_from_form(self, formdata):
        return {'tenant': formdata.get('tenant')[0]}

    async def options_from_form(self, formdata):
        annotations = self.tenant['metadata']['annotations']
        image_policy = annotations.get('dossier.unito.it/image-policy', self.default_image_policy)
        if image_policy == 'profiles':
            profile = formdata.get('profile', [None])[0]
        elif image_policy == 'manual':
            profile = formdata.get('profile', {
                'kubespawner_override': {
                    'image': formdata.get('image')[0] or self.image
                }
            })
        else:
            profile = {
                'kubespawner_override': {
                    'image': self.image
                }
            }
        resource_policy = annotations.get('dossier.unito.it/resource-policy', self.default_resource_policy)
        if resource_policy == 'profiles':
            pass  # TODO: implement
        elif resource_policy == 'manual':
            profile['kubespawner_override'].update({
                'cpu_limit': int(formdata.get('cpu')[0]) or self.cpu_limit,
                'cpu_guarantee': int(formdata.get('cpu')[0]) or self.cpu_guarantee,
                'mem_limit': int(formdata.get('mem')[0]) or self.mem_limit,
                'mem_guarantee': int(formdata.get('mem')[0]) or self.mem_guarantee})
        else:
            for item in self.tenant['spec'].get('limitRanges', {}).get('items', []):
                for limit in item.get('limits', []):
                    if limit.get('type') == 'Container':
                        profile['kubespawner_override'].update({
                            'cpu_limit': _get_resource_amount(
                                limit.get('default', {}).get('cpu', self.cpu_limit), 'element'),
                            'cpu_guarantee': _get_resource_amount(
                                limit.get('defaultRequest', {}).get('cpu', self.cpu_limit), 'element'),
                            'mem_limit': _get_resource_amount(
                                limit.get('default', {}).get('memory', self.mem_limit), 'byte'),
                            'mem_guarantee': _get_resource_amount(
                                limit.get('defaultRequest', {}).get('memory', self.mem_guarantee), 'byte')})
                        break
        self.log.debug("Launching profile " + str(profile))
        return {'profile': profile}
