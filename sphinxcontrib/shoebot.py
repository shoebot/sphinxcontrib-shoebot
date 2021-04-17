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

from hashlib import sha1

import shoebot

# Options
# ~~~~~~~

# Set to True if you want inline CSS styles instead of classes
INLINESTYLES = False

# The default formatter
DEFAULT = HtmlFormatter(noclasses=INLINESTYLES)

# Extra code added to every bot
BOT_PRESET_SOURCE_CODE = """
size{size}
background(1)
"""


def get_hashid(text):
    return sha1(text.encode("utf-8")).hexdigest()


class ShoebotError(SphinxError):
    category = "shoebot error"


def align(argument):
    """Conversion function for the "align" option."""
    return directives.choice(argument, ("left", "center", "right"))


def size_option(argument):
    """Decode the size option"""
    if isinstance(argument, tuple):
        return argument
    if isinstance(argument, str):
        return tuple(map(int, argument.split(",")))
    raise ArgumentError("Expected size to be str or tuple")


class ShoebotDirective(Directive):
    """Source code syntax highlighting."""

    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True

    option_spec = {"alt": str, "filename": str, "size": size_option, "source": str}
    has_content = True

    def run(self):
        self.assert_has_content()

        env = self.state.document.settings.env

        source_code = "\n".join(self.content)
        parsed_code = highlight(source_code, PythonLexer(), HtmlFormatter())
        result = [nodes.raw("", parsed_code, format="html")]

        options_dict = dict(self.options)
        image_size = options_dict.get("size", (100, 100))

        output_image = options_dict.get("filename") or get_hashid(source_code)
        output_dir = os.path.normpath(f"{env.srcdir}/../build-images/examples")

        ensuredir(output_dir)

        script_to_render = BOT_PRESET_SOURCE_CODE.format(size=image_size) + source_code
        output_filename = os.path.join(output_dir, output_image)
        try:
            os.unlink(output_filename)
        except FileNotFoundError:
            pass

        with open(output_filename, "wb") as outfile:
            bot = shoebot.create_bot(buff=outfile, format="png")
            bot.run(script_to_render)

        image_node = nodes.image(uri=f"/../build-images/examples/{output_image}")
        result.insert(0, image_node)

        return result


def setup(app):
    pass


directives.register_directive("shoebot", ShoebotDirective)
