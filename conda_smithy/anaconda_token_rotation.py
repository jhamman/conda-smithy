import os
import sys
from contextlib import redirect_stderr, redirect_stdout

import requests

from .utils import update_conda_forge_config


def rotate_anaconda_token(
    user,
    project,
    feedstock_directory,
    drone=True,
    circle=True,
    travis=True,
    azure=True,
    appveyor=True,
):
    """Rotate the anaconda (binstar) token used by the CI providers

    All exceptions are swallowed and stdout/stderr from this function is
    redirected to `/dev/null`. Sanitized error messages are
    displayed at the end.

    If you need to debug this function, define `DEBUG_ANACONDA_TOKENS` in
    your environment before calling this function.
    """
    # we are swallong all of the logs below, so we do a test import here
    # to generate the proper errors for missing tokens
    # note that these imports cover all providers
    try:
        from .ci_register import anaconda_token
    except ImportError:
        raise RuntimeError(
            "You must have the anaconda token defined to do token rotation!"
        )
    from .ci_register import travis_endpoint  # noqa
    from .azure_ci_utils import default_config  # noqa

    # capture stdout, stderr and suppress all exceptions so we don't
    # spill tokens
    failed = False
    err_msg = None
    with open(os.devnull, "w") as fp:
        if "DEBUG_ANACONDA_TOKENS" in os.environ:
            fpo = sys.stdout
            fpe = sys.stdout
        else:
            fpo = fp
            fpe = fp

        with redirect_stdout(fpo), redirect_stderr(fpe):
            try:
                if circle:
                    try:
                        rotate_token_in_circle(user, project, anaconda_token)
                    except Exception as e:
                        if "DEBUG_ANACONDA_TOKENS" in os.environ:
                            raise e
                        else:
                            err_msg = (
                                "Failed to rotate token for %s/%s"
                                " on circle!"
                            ) % (user, project)
                            failed = True
                            raise RuntimeError(err_msg)

                if drone:
                    try:
                        rotate_token_in_drone(user, project, anaconda_token)
                    except Exception as e:
                        if "DEBUG_ANACONDA_TOKENS" in os.environ:
                            raise e
                        else:
                            err_msg = (
                                "Failed to rotate token for %s/%s" " on drone!"
                            ) % (user, project)
                            failed = True
                            raise RuntimeError(err_msg)

                if travis:
                    try:
                        rotate_token_in_travis(user, project, anaconda_token)
                    except Exception as e:
                        if "DEBUG_ANACONDA_TOKENS" in os.environ:
                            raise e
                        else:
                            err_msg = (
                                "Failed to rotate token for %s/%s"
                                " on travis!"
                            ) % (user, project)
                            failed = True
                            raise RuntimeError(err_msg)

                if azure:
                    try:
                        rotate_token_in_azure(user, project, anaconda_token)
                    except Exception as e:
                        if "DEBUG_ANACONDA_TOKENS" in os.environ:
                            raise e
                        else:
                            err_msg = (
                                "Failed to rotate token for %s/%s" " on azure!"
                            ) % (user, project)
                            failed = True
                            raise RuntimeError(err_msg)

                if appveyor:
                    try:
                        rotate_token_in_appveyor(
                            feedstock_directory, anaconda_token
                        )
                    except Exception as e:
                        if "DEBUG_ANACONDA_TOKENS" in os.environ:
                            raise e
                        else:
                            err_msg = (
                                "Failed to rotate token for %s/%s"
                                " on appveyor!"
                            ) % (user, project)
                            failed = True
                            raise RuntimeError(err_msg)

            except Exception as e:
                if "DEBUG_ANACONDA_TOKENS" in os.environ:
                    raise e
                failed = True
    if failed:
        if err_msg:
            raise RuntimeError(err_msg)
        else:
            raise RuntimeError(
                (
                    "Rotating the feedstock token in proviers for %s/%s failed!"
                    " Try the command locally with DEBUG_ANACONDA_TOKENS"
                    " defined in the environment to investigate!"
                )
                % (user, project)
            )


def rotate_token_in_circle(user, project, binstar_token):
    from .ci_register import circle_token

    url_template = (
        "https://circleci.com/api/v1.1/project/github/{user}/{project}/envvar{extra}?"
        "circle-token={token}"
    )

    r = requests.get(
        url_template.format(
            token=circle_token, user=user, project=project, extra=""
        )
    )
    if r.status_code != 200:
        r.raise_for_status()

    have_binstar_token = False
    for evar in r.json():
        if evar["name"] == "BINSTAR_TOKEN":
            have_binstar_token = True

    if have_binstar_token:
        r = requests.delete(
            url_template.format(
                token=circle_token,
                user=user,
                project=project,
                extra="/BINSTAR_TOKEN",
            )
        )
        if r.status_code != 200:
            r.raise_for_status()

    data = {"name": "BINSTAR_TOKEN", "value": binstar_token}
    response = requests.post(
        url_template.format(
            token=circle_token, user=user, project=project, extra=""
        ),
        data,
    )
    if response.status_code != 201:
        raise ValueError(response)


def rotate_token_in_drone(user, project, binstar_token):
    from .ci_register import drone_session

    session = drone_session()

    r = session.get(f"/api/repos/{user}/{project}/secrets")
    r.raise_for_status()
    have_binstar_token = False
    for secret in r.json():
        if "BINSTAR_TOKEN" == secret["name"]:
            have_binstar_token = True

    if have_binstar_token:
        r = session.patch(
            f"/api/repos/{user}/{project}/secrets/BINSTAR_TOKEN",
            json={"data": binstar_token, "pull_request": False},
        )
        r.raise_for_status()
    else:
        response = session.post(
            f"/api/repos/{user}/{project}/secrets",
            json={
                "name": "BINSTAR_TOKEN",
                "data": binstar_token,
                "pull_request": False,
            },
        )
        if response.status_code != 200:
            response.raise_for_status()


def rotate_token_in_travis(user, project, binstar_token):
    """Add the BINSTAR_TOKEN to travis."""
    from .ci_register import (
        travis_endpoint,
        travis_headers,
        travis_get_repo_info,
    )

    headers = travis_headers()

    repo_info = travis_get_repo_info(user, project)
    repo_id = repo_info["id"]

    r = requests.get(
        "{}/repo/{repo_id}/env_vars".format(travis_endpoint, repo_id=repo_id),
        headers=headers,
    )
    if r.status_code != 200:
        r.raise_for_status()

    have_binstar_token = False
    ev_id = None
    for ev in r.json()["env_vars"]:
        if ev["name"] == "BINSTAR_TOKEN":
            have_binstar_token = True
            ev_id = ev["id"]

    data = {
        "env_var.name": "BINSTAR_TOKEN",
        "env_var.value": binstar_token,
        "env_var.public": "false",
    }

    if have_binstar_token:
        r = requests.patch(
            "{}/repo/{repo_id}/env_var/{ev_id}".format(
                travis_endpoint, repo_id=repo_id, ev_id=ev_id,
            ),
            headers=headers,
            json=data,
        )
        r.raise_for_status()
    else:
        r = requests.post(
            "{}/repo/{repo_id}/env_vars".format(
                travis_endpoint, repo_id=repo_id
            ),
            headers=headers,
            json=data,
        )
        if r.status_code != 201:
            r.raise_for_status()


def rotate_token_in_azure(user, project, binstar_token):
    from .azure_ci_utils import build_client, get_default_build_definition
    from .azure_ci_utils import default_config as config
    from vsts.build.v4_1.models import BuildDefinitionVariable

    bclient = build_client()

    existing_definitions = bclient.get_definitions(
        project=config.project_name, name=project
    )
    if existing_definitions:
        assert len(existing_definitions) == 1
        ed = existing_definitions[0]
    else:
        raise RuntimeError(
            "Cannot add BINSTAR_TOKEN to a repo that is not already registerd on azure CI!"
        )

    if not hasattr(ed, "variables") or ed.variables is None:
        variables = {}
    else:
        variables = ed.variables

    variables["BINSTAR_TOKEN"] = BuildDefinitionVariable(
        allow_override=False, is_secret=True, value=binstar_token,
    )

    build_definition = get_default_build_definition(
        user,
        project,
        config=config,
        variables=variables,
        id=ed.id,
        revision=ed.revision,
    )

    bclient.update_definition(
        definition=build_definition,
        definition_id=ed.id,
        project=ed.project.name,
    )


def rotate_token_in_appveyor(feedstock_directory, binstar_token):
    from .ci_register import appveyor_token

    headers = {"Authorization": "Bearer {}".format(appveyor_token)}
    url = "https://ci.appveyor.com/api/account/encrypt"
    response = requests.post(
        url, headers=headers, data={"plainValue": binstar_token}
    )
    if response.status_code != 200:
        raise ValueError(response)

    with update_conda_forge_config(feedstock_directory) as code:
        code.setdefault("appveyor", {}).setdefault("secure", {})[
            "BINSTAR_TOKEN"
        ] = response.content.decode("utf-8")
