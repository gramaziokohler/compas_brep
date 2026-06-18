import os

from compas_invocations2 import build
from compas_invocations2 import docs
from compas_invocations2 import mkdocs
from compas_invocations2 import style
from compas_invocations2 import tests
from invoke.collection import Collection

ns = Collection(
    docs.help,
    mkdocs.docs,
    style.check,
    style.lint,
    style.format,
    tests.test,
    tests.testdocs,
    tests.testcodeblocks,
    build.prepare_changelog,
    build.clean,
    build.release,
)
ns.configure(
    {
        "base_folder": os.path.dirname(__file__),
        "lint_folders": ["src", "tests"],
        "format_folders": ["src", "tests"],
    }
)
