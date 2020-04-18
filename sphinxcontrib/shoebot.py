# -*- coding: utf-8 -*-
"""
    Derived from the Pygments reStructuredText directive
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    http://docutils.sourceforge.net/docs/howto/rst-directives.html

    :copyright: (for reStructuredText directive ) Pygments Copyright 2006-2009 by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""
import os

from docutils import nodes
from docutils.parsers.rst import directives, Directive

from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import HtmlFormatter

from sphinx.errors import SphinxError
from sphinx.util import ensuredir

try:
    from hashlib import sha1 as sha
except ImportError:
    from sha import sha

import subprocess

# Options
# ~~~~~~~

# Set to True if you want inline CSS styles instead of classes
INLINESTYLES = False

# The default formatter
DEFAULT = HtmlFormatter(noclasses=INLINESTYLES)

BOT_HEADER = """
size{size}
background(1)
fill(.95,.75,0)
"""


def get_hashid(text, options=""):
    hashkey = (text + options).encode("utf-8")
    hashid = sha(hashkey).hexdigest()
    return hashid


class ShoebotError(SphinxError):
    category = "shoebot error"


def align(argument):
    """Conversion function for the "align" option."""
    return directives.choice(argument, ("left", "center", "right"))


def size_opt(argument):
    """Decode the size option"""
    if isinstance(argument, tuple):
        return argument
    else:
        return tuple(map(int, argument.split(",")))


class ShoebotDirective(Directive):
    """ Source code syntax hightlighting.
    """

    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True

    option_spec = {"alt": str, "filename": str, "size": size_opt, "source": str}
    has_content = True

    def run(self):
        self.assert_has_content()

        text = "\n".join(self.content)
        parsed = highlight(text, PythonLexer(), HtmlFormatter())

        result = [nodes.raw("", parsed, format="html")]

        options_dict = dict(self.options)
        opt_size = options_dict.get("size", (100, 100))

        fn = options_dict.get("filename") or "{}.png".format(get_hashid(text))

        env = self.state.document.settings.env
        rel_filename, filename = env.relfn2path(fn)

        outfn = os.path.join(env.app.builder.outdir, "_static", rel_filename)
        ensuredir(os.path.dirname(outfn))
        script_to_render = BOT_HEADER.format(size=opt_size) + text
        if os.path.isfile(outfn):
            raise ShoebotError("File %s exists, not overwriting." % outfn)
        try:
            cmd = ["sbot", "-o", "%s" % outfn, script_to_render]
            subprocess.call(cmd)
        except Exception as e:
            print("oops %e" % e)
            print("cmd: ")
            print(" ".join(cmd))
            raise ShoebotError(str(e))

        image_node = nodes.image(uri="_static/{}".format(rel_filename), alt="test")
        result.insert(0, image_node)

        return result


def setup(app):
    pass


directives.register_directive("shoebot", ShoebotDirective)
