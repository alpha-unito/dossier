import distutils.command.build_py
import distutils.command.sdist
import os
import sys
from abc import ABC
from subprocess import check_call

from setuptools import Command

this_directory = os.path.abspath(os.path.dirname(__file__))
jupyterhub_directory = os.path.join(this_directory, "share", "jupyterhub")
static_directory = os.path.join(jupyterhub_directory, "static", "dossier")


def get_data_files():
    data_files = []
    for d, dirs, filenames in os.walk(jupyterhub_directory):
        rel_d = os.path.relpath(d, this_directory)
        data_files.append((rel_d, [os.path.join(rel_d, f) for f in filenames]))
    return data_files


class BaseCommand(Command, ABC):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def get_inputs(self):
        return []

    def get_outputs(self):
        return []


class css(BaseCommand):
    def should_run(self):
        """Does less need to run?"""
        # from IPython.html.tasks.py

        css_targets = [os.path.join(static_directory, "css", "style.min.css")]
        css_maps = [t + ".map" for t in css_targets]
        targets = css_targets + css_maps
        if not all(os.path.exists(t) for t in targets):
            # some generated files don't exist
            return True
        earliest_target = sorted(os.stat(t).st_mtime for t in targets)[0]

        # check if any .less files are newer than the generated targets
        for dirpath, dirnames, filenames in os.walk(static_directory):
            for f in filenames:
                if f.endswith(".less"):
                    path = os.path.join(static_directory, dirpath, f)
                    timestamp = os.stat(path).st_mtime
                    if timestamp > earliest_target:
                        return True

        return False

    def run(self):
        if not self.should_run():
            print("CSS up-to-date")
            return

        self.run_command("js")
        print("Building CSS with LESS")

        style_less = os.path.join(static_directory, "less", "style.less")
        style_css = os.path.join(static_directory, "css", "style.min.css")
        sourcemap = style_css + ".map"

        args = [
            "npm",
            "run",
            "lessc",
            "--",
            "--clean-css",
            f"--source-map-basepath={static_directory}",
            f"--source-map={sourcemap}",
            "--source-map-rootpath=../",
            style_less,
            style_css,
        ]
        try:
            check_call(args, cwd=this_directory)
        except OSError as e:
            print("Failed to run lessc: %s" % e, file=sys.stderr)
            print("You can install js dependencies with `npm install`", file=sys.stderr)
            raise
        # update data-files in case this created new files
        self.distribution.data_files = get_data_files()
        assert not self.should_run(), "CSS.run failed"


class npm(BaseCommand):
    user_options = []
    node_modules = os.path.join(this_directory, "node_modules")
    bower_dir = os.path.join(static_directory, "components")

    def should_run(self):
        if not os.path.exists(self.bower_dir):
            return True
        if not os.path.exists(self.node_modules):
            return True
        if os.stat(self.bower_dir).st_mtime < os.stat(self.node_modules).st_mtime:
            return True
        return (
            os.stat(self.node_modules).st_mtime
            < os.stat(os.path.join(this_directory, "package.json")).st_mtime
        )

    def run(self):
        if not self.should_run():
            print("NPM dependencies up to date")
            return

        print("Installing JavaScript dependencies with NPM")
        check_call(
            ["npm", "install", "--progress=false", "--unsafe-perm"],
            cwd=this_directory,
        )
        os.utime(self.node_modules)

        os.utime(self.bower_dir)
        # update data-files in case this created new files
        self.distribution.data_files = get_data_files()
        assert not self.should_run(), "NPM.run failed"


class build_py(distutils.command.build_py.build_py):
    def run(self) -> None:
        self.run_command("js")
        self.run_command("css")
        return super().run()


class sdist(distutils.command.sdist.sdist):
    def run(self) -> None:
        self.run_command("js")
        self.run_command("css")
        return super().run()