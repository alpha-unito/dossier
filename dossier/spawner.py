import string
import time

import escapism
from jinja2 import BaseLoader
from jinja2 import Environment
from kubernetes.client import ApiException
from kubespawner import KubeSpawner
from kubespawner.clients import shared_client
from slugify import slugify
from traitlets import Unicode, default


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
            return int(v[:-1])
        else:
            return int(v) * 1000
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

    default_tenant_name = Unicode(
        None,
        config=True,
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
                        >
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
                        >
                    </div>
                </label>
                {% endif %}
            </div>
        {% endfor %}
        </div>
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

    dossier_tenants_form_template = Unicode(
        """
        <style>
        #dossier-tenants-list label p {
            font-weight: normal;
        }
        </style>
        <div class='form-group' id='dossier-tenants-list'>
        {% for tenant in tenants %}
        <label for='tenant-item-{{ tenant.name }}' class='form-control input-group'>
            <div class='col-md-1'>
                <input type='radio' name='tenant' id='tenant-item-{{ tenant.slug }}' value='{{ tenant.slug }}' />
            </div>
            <div class='col-md-11'>
                <strong>{{ tenant.name }}</strong>
                {% if tenant.description %}
                <p>{{ tenant.description }}</p>
                {% endif %}
            </div>
        </label>
        {% endfor %}
        </div>
        """,
        config=True,
        help="""
            Jinja2 template for constructing tenant fomrm shown to user.

            The contents of the `tenants` variable are passed in to the template.
            This should be used to construct the contents of a HTML form. When
            posted, this form is expected to have an item with name `tenant` and
            the value of the index of the tenant in the `tenants` variable.
        """
    )

    async def _ensure_namespace(self):
        safe_chars = set(string.ascii_lowercase + string.digits)
        username = escapism.escape(self.user.name, safe=safe_chars, escape_char='-').lower()
        self.namespace = self.tenant['metadata']['name'] + '-' + username
        namespaces = [n.metadata.name for n in self.api.list_namespace().items]
        if self.namespace not in namespaces:
            await super()._ensure_namespace()
            time.sleep(5)

    def get_tenants(self):
        return self.custom_api.list_cluster_custom_object(
            group="capsule.clastix.io",
            version="v1beta1",
            plural="tenants")['items']

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

    async def get_options_form(self):
        print("Rendering form for tenant {}".format(self.tenant['metadata']['name']))
        annotations = self.tenant['metadata']['annotations']
        image_policy = annotations.get('dossier.unito.it/image-policy', self.default_image_policy)
        profile_options_form = ''
        if image_policy == "profiles":
            if callable(self.profile_list):
                profile_options_form = self._render_options_form_dynamically(self.profile_list)
            else:
                profile_options_form = self._render_options_form(self.profile_list)
        dossier_form_template = Environment(loader=BaseLoader).from_string(
            self.dossier_options_form_template
        )
        resources = {
            'cpu': {'name': 'cpu', 'display_name': 'CPU', 'unit': 'element', 'step': 10},
            'memory': {'name': 'memory', 'display_name': 'Memory', 'unit': 'byte'}
        }
        if 'limitRanges' in self.tenant['spec']:
            for item in self.tenant['spec']['limitRanges']['items']:
                for limit in item['limits']:
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
        else:
            for r in resources:
                resources[r]['min'] = 0
        return dossier_form_template.render(
            image_policy=image_policy,
            profile_options_form=profile_options_form,
            default_image=self.image,
            resources=list(resources.values()))

    def render_tenants_form(self, tenants):
        dossier_form_template = Environment(loader=BaseLoader).from_string(
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

    async def tenant_from_form(self, formdata):
        return {'tenant': formdata.get('tenant')[0]}

    async def options_from_form(self, formdata):
        return {
            'image': formdata.get('image', [None])[0],
            'cpu': formdata.get('cpu')[0],
            'mem': formdata.get('mem')[0]
        }
