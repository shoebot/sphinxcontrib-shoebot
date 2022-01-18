"""
    sphinx.ext.shoebot
    ~~~~~~~~~~~~~~~~~~~

    Allow shoebot-formatted graphs to be included in Sphinx-generated
    documents inline.

    :copyright: Copyright 2007-2022 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""
from hashlib import sha1

import os
import posixpath
import re
import subprocess
from os import path
from subprocess import PIPE, CalledProcessError
from typing import Any, Dict, List, Tuple, Union

from docutils import nodes
from docutils.nodes import Node
from docutils.parsers.rst import Directive, directives

from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import HtmlFormatter, LatexFormatter

import sphinx
from shoebot import create_bot
from sphinx.application import Sphinx
from sphinx.errors import SphinxError
from sphinx.locale import _, __
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective, SphinxTranslator
from sphinx.util.fileutil import copy_asset
from sphinx.util.i18n import search_image_for_language
from sphinx.util.nodes import set_source_info
from sphinx.util.osutil import ensuredir
from sphinx.util.typing import OptionSpec
from sphinx.writers.html import HTMLTranslator
from sphinx.writers.latex import LaTeXTranslator
from sphinx.writers.manpage import ManualPageTranslator
from sphinx.writers.texinfo import TexinfoTranslator
from sphinx.writers.text import TextTranslator

logger = logging.getLogger(__name__)


class ShoebotError(SphinxError):
    category = 'Shoebot error'


# class shoebot_code(nodes.General, nodes.Inline, nodes.Element):
#     pass


class shoebot(nodes.General, nodes.Inline, nodes.Element):
    pass


def figure_wrapper(directive: Directive, node: shoebot, caption: str) -> nodes.figure:
    figure_node = nodes.figure('', node)
    if 'align' in node:
        figure_node['align'] = node.attributes.pop('align')

    inodes, messages = directive.state.inline_text(caption, directive.lineno)
    caption_node = nodes.caption(caption, '', *inodes)
    caption_node.extend(messages)
    set_source_info(directive, caption_node)
    figure_node += caption_node
    return figure_node


def align_spec(argument: Any) -> str:
    return directives.choice(argument, ('left', 'center', 'right'))


def size_spec(argument):
    """Decode the size option"""
    if isinstance(argument, tuple):
        return argument
    if isinstance(argument, str):
        return tuple(map(int, argument.split(",")))
    raise ValueError("Expected size to be str or tuple")


def ximports_spec(argument):
    """Decode the ximports option"""
    if isinstance(argument, str):
        return [l for l in argument.strip(" ()").split(",") if l]
    raise ValueError("Expected a comma-separated list of libraries")


class Shoebot(SphinxDirective):
    """
    Directive to insert arbitrary shoebot markup.
    """
    has_content = True
    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = False
    option_spec: OptionSpec = {
        'alt': directives.unchanged,
        'align': align_spec,
        # 'caption': directives.unchanged,
        # 'layout': directives.unchanged,
        # 'name': directives.unchanged,
        # 'class': directives.class_option,
        'size': size_spec,
        'ximports': ximports_spec,
        'filename': directives.unchanged,  # TODO - remove.
    }

    def run(self) -> List[Node]:
        if self.arguments:
            document = self.state.document
            if self.content:
                return [document.reporter.warning(
                    __('Shoebot directive cannot have both content and '
                       'a filename argument'), line=self.lineno)]

            # TODO - filename as first param, should add search paths
            #        so this can work with examples.
            raise NotImplemented('TODO filename as first param')
            # rel_filename, filename = self.env.relfn2path(self.arguments[0])
            # self.env.note_dependency(rel_filename)
            # try:
            #     with open(filename, encoding='utf-8') as fp:
            #         source_code = fp.read()
            # except OSError:
            #     return [document.reporter.warning(
            #         __('External Shoebot file %r not found or reading '
            #            'it failed') % filename, line=self.lineno)]
        else:
            source_code = '\n'.join(self.content)
            rel_filename = None
            if not source_code.strip():
                return [self.state_machine.reporter.warning(
                    __('Ignoring "shoebot" directive without content.'),
                    line=self.lineno)]

        node = shoebot()
        node['code'] = source_code
        node['options'] = {'docname': self.env.docname}

        # TODO - can support external shoebot ??
        # if 'shoebot_cmd' in self.options:
        #     node['options']['shoebot_cmd'] = self.options['shoebot_cmd']
        # if 'layout' in self.options:
        #     node['options']['shoebot_cmd'] = self.options['layout']
        if 'alt' in self.options:
            node['alt'] = self.options['alt']
        if 'align' in self.options:
            node['align'] = self.options['align']
        # if 'class' in self.options:
        #     node['classes'] = self.options['class']
        if rel_filename:
            node['filename'] = rel_filename

        # if 'caption' not in self.options:
        self.add_name(node)
        return [node]
        # else:
        #     figure = figure_wrapper(self, node, self.options['caption'])
        #     self.add_name(figure)
        #     return [figure]


def get_hashid(text):
    return sha1(text.encode("utf-8")).hexdigest().encode('utf-8')


def render_shoebot(self: SphinxTranslator, code: str, options: Dict, format: str,
               prefix: str = 'shoebot', filename: str = None) -> Union[
    tuple[str, Union[bytes, str]], tuple[None, None]]:
    """Render shoebot code into a PNG or PDF output file."""
    #shoebot_cmd = options.get('shoebot_cmd', self.builder.config.shoebot_cmd)
    shoebot_cmd = 'sbot'
    size = options.get("size", (100, 100))
    ximports = options.get('ximports', [])
    #hashkey = (code + str(options) + str(shoebot_cmd) +
    #           str(self.builder.config.shoebot_cmd_args)).encode()
    hashkey = get_hashid(code)

    fname = '%s-%s.%s' % (prefix, sha1(hashkey).hexdigest(), format)
    relfn = posixpath.join(self.builder.imgpath, fname)
    outfn = path.join(self.builder.outdir, self.builder.imagedir, fname)

    if path.isfile(outfn):
        return relfn, outfn

    if (hasattr(self.builder, '_shoebot_warned_shoebot') and
       self.builder._shoebot_warned_shoebot.get(shoebot_cmd)):  # type: ignore  # NOQA
        return None, None

    ensuredir(path.dirname(outfn))

    # shoebot_args = [shoebot_cmd]
    # shoebot_args.extend(self.builder.config.shoebot_cmd_args)
    # shoebot_args.extend(['-T' + format, '-o' + outfn])

    docname = options.get('docname', 'index')
    if filename:
        cwd = path.dirname(path.join(self.builder.srcdir, filename))
    else:
        cwd = path.dirname(path.join(self.builder.srcdir, docname))

    _cwd = os.getcwd()
    os.chdir(cwd)
    with open(outfn, "wb") as f:
        bot = create_bot(buff=f, format=format)
        bot.size(*size)
        bot.background(1)
        for libname in ximports:
            bot.ximport(libname)
        bot.run(code)

    os.chdir(_cwd)

    # if format == 'png':
    #     shoebot_args.extend(['-Tcmapx', '-o%s.map' % outfn])
    #
    # try:
    #     ret = subprocess.run(shoebot_args, input=code.encode(), stdout=PIPE, stderr=PIPE,
    #                          cwd=cwd, check=True)
    if True:
        if not path.isfile(outfn):
            raise ShoebotError(__('shoebot did not produce an output file: %s %s' % (_cwd, outfn)))
            # raise ShoebotError(__('shoebot did not produce an output file:\n[stderr]\n%r\n'
            #                        '[stdout]\n%r') % (ret.stderr, ret.stdout))
        return relfn, outfn
    # except OSError:
    #     logger.warning(__('shoebot command %r cannot be run (needed for shoebot '
    #                       'output), check the shoebot_cmd setting'), shoebot_cmd)
    #     if not hasattr(self.builder, '_shoebot_warned_shoebot'):
    #         self.builder._shoebot_warned_shoebot = {}  # type: ignore
    #     self.builder._shoebot_warned_shoebot[shoebot_cmd] = True  # type: ignore
    #     return None, None
    # except CalledProcessError as exc:
    #     raise ShoebotError(__('shoebot exited with error:\n[stderr]\n%r\n'
    #                            '[stdout]\n%r') % (exc.stderr, exc.stdout)) from exc


def render_shoebot_html(self: HTMLTranslator, node: shoebot, code: str, options: Dict,
                    prefix: str = 'shoebot', imgcls: str = None, alt: str = None,
                    filename: str = None) -> Tuple[str, str]:

    format = self.builder.config.shoebot_output_format
    try:
        if format not in ('png', 'svg'):
            raise ShoebotError(__("shoebot_output_format must be one of 'png', "
                                   "'svg', but is %r") % format)
        fname, outfn = render_shoebot(self, code, options, format, prefix, filename)
    except ShoebotError as exc:
        logger.warning(__('shoebot code %r: %s'), code, exc)
        raise nodes.SkipNode from exc

    classes = [imgcls, 'shoebot'] + node.get('classes', [])
    imgcls = ' '.join(filter(None, classes))

    if fname is None:
        self.body.append(self.encode(code))
    else:
        parsed_code = highlight(code, PythonLexer(), HtmlFormatter())  # Copied from shoebot
        if alt is None:
            alt = node.get('alt', self.encode(code).strip())
        if 'align' in node:
            self.body.append('<div align="%s" class="align-%s">' %
                             (node['align'], node['align']))
        if format == 'svg':
            self.body.append('<div class="shoebot">')
            self.body.append('<object data="%s" type="image/svg+xml" class="%s">\n' %
                             (fname, imgcls))
            self.body.append('<p class="warning">%s</p>' % alt)
            self.body.append('</object>\n')
            self.body.append(parsed_code + '\n')
            self.body.append('</div>\n')
        elif format == 'png':
            self.body.append('<div class="shoebot">')
            self.body.append('<img src="%s" alt="%s" class="%s" />' %
                             (fname, alt, imgcls))
            self.body.append(parsed_code + '\n')
            self.body.append('</div>\n')
        else:
            raise NotImplemented('Format not implemented %s' % format)
            # with open(outfn + '.map', encoding='utf-8') as mapfile:
            #         #                imgmap = ClickableMapDefinition(outfn + '.map', mapfile.read(), shoebot=code)
            #         #                if imgmap.clickable:
            #         #                    # has a map
            #         #                    self.body.append('<div class="shoebot">')
            #         #                    self.body.append('<img src="%s" alt="%s" usemap="#%s" class="%s" />' %
            #         #                                     (fname, alt, imgmap.id, imgcls))
            #         #                    self.body.append('</div>\n')
            #         #                    self.body.append(imgmap.generate_clickable_map())
            #         #                else:
            #         # nothing in image map
            #         self.body.append('<div class="shoebot">')
            #         self.body.append('<img src="%s" alt="%s" class="%s" />' %
            #                          (fname, alt, imgcls))
            #         self.body.append('</div>\n')
            pass
        if 'align' in node:
            self.body.append('</div>\n')

    # import ipdb
    # with ipdb.launch_ipdb_on_exception():

    raise nodes.SkipNode


def html_visit_shoebot(self: HTMLTranslator, node: shoebot) -> None:
    render_shoebot_html(self, node, node['code'], node['options'], filename=node.get('filename'))

# def html_visit_shoebot_code(self: HTMLTranslator, node: shoebot) -> None:
#     render_shoebot_code_html(self, node, node['code'], node['options'], filename=node.get('filename'))

#def render_shoebot_latex(self: LaTeXTranslator, node: shoebot, code: str,
#                     options: Dict, prefix: str = 'shoebot', filename: str = None
#                     ) -> None:
#    try:
#        fname, outfn = render_shoebot(self, code, options, 'pdf', prefix, filename)
#    except ShoebotError as exc:
#        logger.warning(__('shoebot code %r: %s'), code, exc)
#        raise nodes.SkipNode from exc

#    is_inline = self.is_inline(node)

#    if not is_inline:
#        pre = ''
#        post = ''
#        if 'align' in node:
#            if node['align'] == 'left':
#                pre = '{'
#                post = r'\hspace*{\fill}}'
#            elif node['align'] == 'right':
#                pre = r'{\hspace*{\fill}'
#                post = '}'
#            elif node['align'] == 'center':
#                pre = r'{\hfill'
#                post = r'\hspace*{\fill}}'
#        self.body.append('\n%s' % pre)

#    self.body.append(r'\sphinxincludegraphics[]{%s}' % fname)

#    if not is_inline:
#        self.body.append('%s\n' % post)

#    raise nodes.SkipNode


#def latex_visit_shoebot(self: LaTeXTranslator, node: shoebot) -> None:
#    render_shoebot_latex(self, node, node['code'], node['options'], filename=node.get('filename'))


#def render_shoebot_texinfo(self: TexinfoTranslator, node: shoebot, code: str,
#                       options: Dict, prefix: str = 'shoebot') -> None:
#    try:
#        fname, outfn = render_shoebot(self, code, options, 'png', prefix)
#    except ShoebotError as exc:
#        logger.warning(__('shoebot code %r: %s'), code, exc)
#        raise nodes.SkipNode from exc
#    if fname is not None:
#        self.body.append('@image{%s,,,[shoebot],png}\n' % fname[:-4])
#    raise nodes.SkipNode


#def texinfo_visit_shoebot(self: TexinfoTranslator, node: shoebot) -> None:
#    render_shoebot_texinfo(self, node, node['code'], node['options'])


def text_visit_shoebot(self: TextTranslator, node: shoebot) -> None:
    if 'alt' in node.attributes:
        self.add_text(_('[shoebot: %s]') % node['alt'])
    else:
        self.add_text(_('[shoebot]'))
    raise nodes.SkipNode


def man_visit_shoebot(self: ManualPageTranslator, node: shoebot) -> None:
    if 'alt' in node.attributes:
        self.body.append(_('[shoebot: %s]') % node['alt'])
    else:
        self.body.append(_('[shoebot]'))
    raise nodes.SkipNode


def on_build_finished(app: Sphinx, exc: Exception) -> None:
    #    if exc is None and app.builder.format == 'html':
    #        src = path.join(sphinx.package_dir, 'templates', 'shoebot', 'shoebot.css')
    #        dst = path.join(app.outdir, '_static')
    #        copy_asset(src, dst)
    pass


def setup(app: Sphinx) -> Dict[str, Any]:
    app.add_node(shoebot,
                 html=(html_visit_shoebot, None),
                 #latex=(latex_visit_shoebot, None),
                 #texinfo=(texinfo_visit_shoebot, None),
                 text=(text_visit_shoebot, None),
                 man=(man_visit_shoebot, None))
    # app.add_node(shoebot_code,
    #              html=(html_visit_shoebot_code, None),
    #              ))
    app.add_directive('shoebot', Shoebot)
    #app.add_config_value('shoebot_cmd', 'shoebot', 'html')
    #app.add_config_value('shoebot_cmd_args', [], 'html')
    app.add_config_value('shoebot_output_format', 'png', 'html')
    #app.add_css_file('shoebot.css')
    app.connect('build-finished', on_build_finished)
    return {'version': sphinx.__display_version__, 'parallel_read_safe': True}
