from kubernetes_asyncio.client import ApiException
from kubespawner.clients import shared_client


def get_spawner(name):
    try:
        api = shared_client("CustomObjectsApi")
        return api.get_cluster_custom_object(
            group="dossier.unito.it",
            version="v1alpha1",
            plural="spawners",
            name=name)
    except ApiException as error:
        if error.status == 404:
            return None
        else:
            raise error


def get_spawners():
    api = shared_client("CustomObjectsApi")
    return api.list_cluster_custom_object(
        group="dossier.unito.it",
        version="v1alpha1",
        plural="spawners")['items']


def get_tenant(name):
    try:
        api = shared_client("CustomObjectsApi")
        return api.get_cluster_custom_object(
            group="capsule.clastix.io",
            version="v1beta1",
            plural="tenants",
            name=name)
    except ApiException as error:
        if error.status == 404:
            return None
        else:
            raise error


def get_tenants():
    api = shared_client("CustomObjectsApi")
    return api.list_cluster_custom_object(
        group="capsule.clastix.io",
        version="v1beta1",
        plural="tenants")['items']
