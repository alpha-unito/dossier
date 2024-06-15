from __future__ import annotations

import os
import shutil
from tempfile import TemporaryDirectory
from textwrap import dedent

import asyncssh
from jupyterhub.spawner import Spawner
from jupyterhub.utils import url_path_join
from traitlets.traitlets import Bool, Dict, Integer, Unicode


class SSHSpawner(Spawner):
    remote_host = Unicode(help="SSH remote host to spawn sessions on", config=True)

    remote_port = Unicode("22", help="SSH remote port number", config=True)

    ssh_command = Unicode("/usr/bin/ssh", help="Actual SSH command", config=True)

    path = Unicode(
        "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:~/.local/bin",
        help="Default PATH (should include jupyter and python)",
        config=True,
    )

    # The get_port.py script is in scripts/get_port.py
    # FIXME See if we avoid having to deploy a script on remote side?
    # For instance, we could just install sshspawner on the remote side
    # as a package and have it put get_port.py in the right place.
    # If we were fancy it could be configurable so it could be restricted
    # to specific ports.
    remote_port_command = Unicode(
        "/usr/bin/python /usr/local/bin/get_port.py",
        help="Command to return unused port on remote host",
        config=True,
    )

    # FIXME Fix help, what happens when not set?
    hub_api_url = Unicode(
        "",
        help=dedent(
            """If set, Spawner will configure the containers to use
            the specified URL to connect the hub api. This is useful when the
            hub_api is bound to listen on all ports or is running inside of a
            container."""
        ),
        config=True,
    )

    ssh_keyfile = Unicode(
        "~/.ssh/id_rsa",
        help=dedent(
            """Key file used to authenticate hub with remote host.

            `~` will be expanded to the user's home directory and `{username}`
            will be expanded to the user's username"""
        ),
        config=True,
    )

    pid = Integer(
        0,
        help=dedent(
            """Process ID of single-user server process spawned for
            current user."""
        ),
    )

    resource_path = Unicode(
        ".jupyterhub-resources",
        help=dedent(
            """The base path where all necessary resources are
            placed. Generally left relative so that resources are placed into
            this base directory in the user's home directory."""
        ),
        config=True,
    )

    # Options to specify whether the Spawner should enable the client to
    # create a backward ssh tunnnel to the JupyterHub instance
    ssh_backtunnel_client = Bool(default=False, config=True)

    # Where on the client the backtunnel ssh keys should be placed
    ssh_backtunnel_client_path = Unicode("~/.ssh", config=True)

    ssh_forward_credentials_paths = Dict(
        {"private_key_file": "", "public_key_file": ""},
        config=True,
        help="The path to the credentials that should be "
        "copied to the Notebook during the spawn",
    )

    async def _transfer(self, username, key, certificate, local_resource_path, dst):
        # create resource path dir in user's home on remote
        async with asyncssh.connect(
            self.remote_host,
            username=username,
            client_keys=[(key, certificate)],
            known_hosts=None,
        ) as conn:
            mkdir_cmd = f"mkdir -p {dst} 2>/dev/null"
            _ = await conn.run(mkdir_cmd)

        # copy files
        files = [
            os.path.join(local_resource_path, f)
            for f in os.listdir(local_resource_path)
        ]
        async with asyncssh.connect(
            self.remote_host,
            username=username,
            client_keys=[(key, certificate)],
            known_hosts=None,
        ) as conn:
            await asyncssh.scp(files, (conn, dst))

    def load_state(self, state):
        """Restore state about ssh-spawned server after a hub restart.

        The ssh-spawned processes need IP and the process id."""
        super().load_state(state)
        if "pid" in state:
            self.pid = state["pid"]
        if "remote_host" in state:
            self.remote_host = state["remote_host"]

    def get_state(self):
        """Save state needed to restore this spawner instance after hub restore.

        The ssh-spawned processes need IP and the process id."""
        state = super().get_state()
        if self.pid:
            state["pid"] = self.pid
        return state

    def clear_state(self):
        """Clear stored state about this spawner (ip, pid)"""
        super().clear_state()
        self.pid = 0

    async def start(self):
        """Start single-user server on remote host."""
        username = self.user.name
        kf = self.ssh_keyfile.format(username=username)
        cf = kf + "-cert.pub"
        k = asyncssh.read_private_key(kf)
        c = asyncssh.read_certificate(cf)

        self.remote_host, port = await self.remote_random_port()

        if self.remote_host is None or port is None or port == 0:
            return False
        self.remote_port = str(port)

        cmd = []
        cmd.extend(self.cmd)
        cmd.extend(self.get_args())

        if self.user.settings["internal_ssl"]:
            with TemporaryDirectory() as td:
                local_resource_path = td
                self.cert_paths = self.stage_certs(self.cert_paths, local_resource_path)
                await self._transfer(
                    username=username,
                    key=k,
                    certificate=c,
                    local_resource_path=local_resource_path,
                    dst=self.resource_path,
                )

        if self.ssh_backtunnel_client:
            with TemporaryDirectory() as td:
                local_resource_path = td
                _ = self.stage_ssh_keys(
                    self.ssh_forward_credentials_paths, local_resource_path
                )
                await self._transfer(
                    username=username,
                    key=k,
                    certificate=c,
                    local_resource_path=local_resource_path,
                    dst=self.ssh_backtunnel_client_path,
                )

        if self.hub_api_url != "":
            old = f"--hub-api-url={self.hub.api_url}"
            new = f"--hub-api-url={self.hub_api_url}"
            for index, value in enumerate(cmd):
                if value == old:
                    cmd[index] = new
        for index, value in enumerate(cmd):
            if value[0:6] == "--port":
                cmd[index] = "--port=%d" % (port)

        remote_cmd = " ".join(cmd)

        self.pid = await self.exec_notebook(remote_cmd)

        self.log.debug(f"Starting User: {self.user.name}, PID: {self.pid}")

        if self.pid < 0:
            return None

        return self.remote_host, port

    async def poll(self):
        """Poll ssh-spawned process to see if it is still running.

        If it is still running return None. If it is not running return exit
        code of the process if we have access to it, or 0 otherwise."""

        if not self.pid:
            # no pid, not running
            self.clear_state()
            return 0

        # send signal 0 to check if PID exists
        alive = await self.remote_signal(0)
        self.log.debug(f"Polling returned {alive}")

        if not alive:
            self.clear_state()
            return 0
        else:
            return None

    async def stop(self, now=False):
        """Stop single-user server process for the current user."""
        _ = await self.remote_signal(15)
        self.clear_state()

    def get_remote_user(self, username):
        """Map JupyterHub username to remote username."""
        return username

    # FIXME this needs to now return IP and port too
    async def remote_random_port(self):
        """Select unoccupied port on the remote host and return it.

        If this fails for some reason return `None`."""

        username = self.get_remote_user(self.user.name)
        kf = self.ssh_keyfile.format(username=username)
        cf = kf + "-cert.pub"
        k = asyncssh.read_private_key(kf)
        c = asyncssh.read_certificate(cf)
        self.log.debug(
            "Connecting to {}@{}:{} using key {} and certificate {}".format(
                username, self.remote_host, self.remote_port, kf, cf
            )
        )

        # this needs to be done against remote_host, first time we're calling up
        async with asyncssh.connect(
            self.remote_host, username=username, client_keys=[(k, c)], known_hosts=None
        ) as conn:
            result = await conn.run(self.remote_port_command)
            stdout = result.stdout
            stderr = result.stderr
            retcode = result.exit_status

        if stdout != b"":
            port = stdout
            port = int(port)
            self.log.debug(f"port={port}")
        else:
            port = None
            self.log.error("Failed to get a remote port")
            self.log.error(f"STDERR={stderr}")
            self.log.debug(f"EXITSTATUS={retcode}")

        ip = self.remote_host
        return ip, port

    # FIXME add docstring
    async def exec_notebook(self, command):
        """TBD"""

        env = super().get_env()
        env["JUPYTERHUB_API_URL"] = self.hub_api_url
        env["JUPYTERHUB_ACTIVITY_URL"] = url_path_join(
            self.hub_api_url,
            "users",
            getattr(self.user, "escaped_name", self.user.name),
            "activity",
        )
        env["PATH"] = self.path
        username = self.get_remote_user(self.user.name)
        kf = self.ssh_keyfile.format(username=username)
        cf = kf + "-cert.pub"
        k = asyncssh.read_private_key(kf)
        c = asyncssh.read_certificate(cf)
        bash_script_str = "#!/bin/bash\n"

        for item in env.items():
            # item is a (key, value) tuple
            # command = ('export %s=%s;' % item) + command
            bash_script_str += "export %s=%s\n" % item
        bash_script_str += "unset XDG_RUNTIME_DIR\n"

        bash_script_str += "touch .jupyter.log\n"
        bash_script_str += "chmod 600 .jupyter.log\n"
        bash_script_str += "%s < /dev/null >> .jupyter.log 2>&1 & pid=$!\n" % command
        bash_script_str += "echo $pid\n"

        run_script = f"/tmp/{self.user.name}_run.sh"
        with open(run_script, "w") as f:
            f.write(bash_script_str)
        if not os.path.isfile(run_script):
            raise Exception("The file " + run_script + "was not created.")
        else:
            with open(run_script) as f:
                self.log.debug(run_script + " was written as:\n" + f.read())

        async with asyncssh.connect(
            self.remote_host, username=username, client_keys=[(k, c)], known_hosts=None
        ) as conn:
            result = await conn.run("bash -s", stdin=run_script)
            stdout = result.stdout
            _ = result.stderr
            retcode = result.exit_status

        self.log.debug(f"exec_notebook status={retcode}")
        if stdout != b"":
            pid = int(stdout)
        else:
            return -1

        return pid

    async def remote_signal(self, sig):
        """Signal on the remote host."""

        username = self.get_remote_user(self.user.name)
        kf = self.ssh_keyfile.format(username=username)
        cf = kf + "-cert.pub"
        k = asyncssh.read_private_key(kf)
        c = asyncssh.read_certificate(cf)

        command = "kill -s %s %d < /dev/null" % (sig, self.pid)

        async with asyncssh.connect(
            self.remote_host, username=username, client_keys=[(k, c)], known_hosts=None
        ) as conn:
            result = await conn.run(command)
            stdout = result.stdout
            stderr = result.stderr
            retcode = result.exit_status
        self.log.debug(
            "command: {} returned {} --- {} --- {}".format(
                command, stdout, stderr, retcode
            )
        )
        return retcode == 0

    def stage_ssh_keys(self, paths, dest):
        shutil.copy(paths["private_key_file"], dest)
        shutil.copy(paths["public_key_file"], dest)

        private_key_file = os.path.basename(paths["private_key_file"])
        public_key_file = os.path.basename(paths["public_key_file"])

        private_key_path = os.path.join(
            self.ssh_backtunnel_client_path, private_key_file
        )
        public_key_path = os.path.join(self.ssh_backtunnel_client_path, public_key_file)

        return {
            "private_key_path": private_key_path,
            "public_key_path": public_key_path,
        }

    def stage_certs(self, paths, dest):
        shutil.move(paths["keyfile"], dest)
        shutil.move(paths["certfile"], dest)
        shutil.copy(paths["cafile"], dest)

        key_base_name = os.path.basename(paths["keyfile"])
        cert_base_name = os.path.basename(paths["certfile"])
        ca_base_name = os.path.basename(paths["cafile"])

        key = os.path.join(self.resource_path, key_base_name)
        cert = os.path.join(self.resource_path, cert_base_name)
        ca = os.path.join(self.resource_path, ca_base_name)

        return {
            "keyfile": key,
            "certfile": cert,
            "cafile": ca,
        }
