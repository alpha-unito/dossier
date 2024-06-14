from kubernetes_asyncio.client import ApiException


async def get_spawner(api, name):
    try:
        return await api.get_cluster_custom_object(
            group="dossier.unito.it", version="v1alpha1", plural="spawners", name=name
        )
    except ApiException as error:
        if error.status == 404:
            return None
        else:
            raise error


async def get_spawners(api):
    return (
        await api.list_cluster_custom_object(
            group="dossier.unito.it", version="v1alpha1", plural="spawners"
        )
    )["items"]


async def get_tenant(api, name):
    try:
        return await api.get_cluster_custom_object(
            group="capsule.clastix.io", version="v1beta2", plural="tenants", name=name
        )
    except ApiException as error:
        if error.status == 404:
            return None
        else:
            raise error


async def get_tenants(api):
    return (
        await api.list_cluster_custom_object(
            group="capsule.clastix.io", version="v1beta2", plural="tenants"
        )
    )["items"]
