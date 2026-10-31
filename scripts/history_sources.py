"""Render history evidence references without treating arbitrary prose as a path."""
import html


def render_history_source(root, source, repository):
    label = html.escape(source)
    if source.startswith(('https://github.com/relcom-technologies/',
                          'https://www.rfc-editor.org/', 'https://archive.org/',
                          'https://ipvx.org/')):
        target = source
    else:
        try:
            local_file = (root / source).is_file()
        except (OSError, ValueError):
            # Evidence may be prose. Linux rejects overlong filename components;
            # invalid path strings must still remain visible as attributed text.
            local_file = False
        target = repository + '/blob/main/' + source if local_file else None
    if target is not None:
        return '<li><a href="' + html.escape(target, quote=True) + '">' + label + '</a></li>'
    return '<li>' + label + '</li>'
